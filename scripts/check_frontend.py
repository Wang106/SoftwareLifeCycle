"""Read-only frontend access checks for approved sample deployments.

This checks HTTP/SSR and disabled authentication, not real browser or provider
acceptance. It never sends credentials, follows redirects or changes edge policy.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

USER_AGENT = 'SoftwareLifeCycle-DeploymentCheck/1.0'
MAX_BODY = 512 * 1024
MAX_TIMEOUT = 30


def approved_origin(value):
    try:
        url = urlsplit(value)
        hostname = url.hostname or ''
        label = hostname.split('.')[0]
        preview = re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?-softwarelifecycle\.whf969\.workers\.dev', hostname)
        if (url.scheme != 'https' or url.username is not None or url.password is not None or
                url.port not in (None, 443) or url.path not in ('', '/') or url.query or url.fragment or
                value != value.strip() or any(ord(ch) < 33 or ord(ch) == 127 for ch in value) or
                (hostname != 'softwarelifecycle.whf969.com' and (not preview or len(label) > 63))):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('Use the approved HTTPS SoftwareLifeCycle origin without credentials, path, query or fragment') from None
    return 'https://' + hostname


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AccountHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.language = None
        self.login_form = False
        self.hidden = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'html':
            self.language = attributes.get('lang')
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'form' and urlsplit(attributes.get('action', '')).path == '/auth/login':
            self.login_form = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def edge_error(status, headers, body):
    if status not in (403, 530):
        return None
    plain = body.strip().lower()
    is_cloudflare = headers.get('server', '').lower() == 'cloudflare' or 'cf-ray' in headers
    # Cloudflare's standard page places Error and its code in separate spans.
    headings = ' '.join(re.sub(r'<[^>]*>', ' ', value) for value in re.findall(r'<h1\b[^>]*>(.*?)</h1>', plain, re.S))
    for code in ('1010', '1020'):
        if (re.fullmatch(r'error code:\s*'+code, plain) or
                (is_cloudflare and re.search(r'\berror(?:\s+code)?\s*:?\s*'+code+r'\b', plain+' '+headings))):
            return 'cloudflare_'+code
    # CF-Ray/Server also appear on proxied origin403 responses.
    generated_error = 'cf-error-origin' in headers or ('cloudflare' in plain and 'cf-error-details' in plain)
    return 'cloudflare_denied' if is_cloudflare and generated_error else None


def diagnostic_headers(headers):
    # Whitelist metadata; never record cookies, authorization, locations or bodies.
    names = ('cf-ray', 'server', 'cf-error-type', 'cf-error-origin', 'cache-control')
    return {name: ''.join(ch for ch in headers[name][:256] if 32 <= ord(ch) < 127)
            for name in names if name in headers}


def fetch_response(opener, url, language, timeout):
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html' if language else 'application/json',
               'Cache-Control': 'no-cache'}
    if language:
        headers['Cookie'] = 'slc_language='+language  # Preference only; no session.
    request = Request(url, headers=headers, method='GET')
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        data = response.read(MAX_BODY + 1)
        if len(data) > MAX_BODY:
            raise ValueError('response_too_large')
        return response.status, {key.lower(): value for key, value in response.headers.items()}, data.decode('utf-8', errors='strict')


def inspect_response(path, language, expected_status, status, headers, body):
    result = {'path': path, 'language': language, 'expected_status': expected_status,
              'status': status, 'headers': diagnostic_headers(headers), 'passed': False}
    edge = edge_error(status, headers, body)
    if edge:
        result['classification'] = edge
        return result
    if 300 <= status < 400:
        result['classification'] = 'redirect_not_followed'
        return result
    if status != expected_status:
        result['classification'] = 'unexpected_status'
        return result
    if 'no-store' not in {part.strip().lower() for part in headers.get('cache-control', '').split(',')}:
        result['classification'] = 'missing_no_store'
        return result
    if language:
        if headers.get('content-type', '').split(';')[0].strip().lower() != 'text/html':
            result['classification'] = 'invalid_html_response'
            return result
        html = AccountHTML(); html.feed(body); html.close()
        message = '此环境暂未开放登录。' if language == 'zh' else 'Login is not available in this environment.'
        expected_language = 'zh-CN' if language == 'zh' else 'en'
        if html.language != expected_language or message not in ''.join(html.text) or html.login_form:
            result['classification'] = 'unexpected_account_state'
            return result
    else:
        if ('private' not in {part.strip().lower() for part in headers.get('cache-control', '').split(',')} or
                'cookie' not in {part.strip().lower() for part in headers.get('vary', '').split(',')} or
                headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json'):
            result['classification'] = 'invalid_private_response'
            return result
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            result['classification'] = 'invalid_json_response'
            return result
        expected_error = 'method_not_allowed' if expected_status == 405 else 'login_not_configured'
        if data != {'error': expected_error} or (expected_status == 405 and headers.get('allow') != 'POST'):
            result['classification'] = 'unexpected_auth_state'
            return result
    result.update(passed=True, classification='passed')
    return result


def check(origin, *, opener=None, timeout=10):
    origin = approved_origin(origin)  # Reject targets before creating a client.
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= MAX_TIMEOUT:
        raise ValueError('Timeout must be greater than0 and at most30 seconds')
    opener = opener if opener is not None else build_opener(NoRedirect())
    probes = [('/account', 'zh', 200), ('/account', 'en', 200),
              ('/auth/session', None, 503), ('/auth/callback', None, 503), ('/auth/login', None, 405)]
    results = []
    for path, language, expected in probes:
        try:
            status, headers, body = fetch_response(opener, origin+path, language, timeout)
            results.append(inspect_response(path, language, expected, status, headers, body))
        except (URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
            classification = 'response_too_large' if isinstance(exc, ValueError) and str(exc) == 'response_too_large' else 'request_failed'
            results.append({'path': path, 'language': language, 'expected_status': expected,
                            'status': None, 'headers': {}, 'passed': False, 'classification': classification})
    return {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'origin': origin, 'user_agent': USER_AGENT, 'expected_mode': 'authentication_disabled',
            'scope': 'http_and_ssr', 'browser_provider_acceptance': 'not_checked',
            'all_passed': all(result['passed'] for result in results), 'results': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('origin')
    parser.add_argument('--output', type=Path, help='Save JSON evidence without response bodies or credentials')
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args(argv)
    try:
        report = check(args.origin, timeout=args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    content = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8')
    print(content, end='')
    return 0 if report['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
