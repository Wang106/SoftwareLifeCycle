'use client';

import { cloneElement, createContext, isValidElement, ReactElement, ReactNode, useContext, useEffect, useState } from 'react';
import { Locale, translateText } from '../lib/i18n';

const LanguageContext = createContext<Locale>('zh');

export function LanguageProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);
  useEffect(() => {
    document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en';
    document.title = locale === 'zh' ? 'SoftwareLifeCycle · 软件生命周期治理' : 'SoftwareLifeCycle · Software lifecycle governance';
  }, [locale]);
  function choose(next: Locale) {
    setLocale(next);
    document.cookie = `slc_language=${next}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
  }
  return <LanguageContext.Provider value={locale}>
    <div className="language-switch" role="group" aria-label={locale === 'zh' ? '界面语言' : 'Interface language'}>
      <button type="button" lang="zh-CN" aria-pressed={locale === 'zh'} onClick={() => choose('zh')}>中文</button>
      <button type="button" lang="en" aria-pressed={locale === 'en'} onClick={() => choose('en')}>English</button>
    </div>
    {children}
  </LanguageContext.Provider>;
}

function textChildren(children: ReactNode, locale: Locale): ReactNode {
  if (typeof children === 'string') return translateText(children, locale);
  if (Array.isArray(children)) return children.map(child => textChildren(child, locale));
  return children;
}

/** Presentation only: never changes values, URLs, keys, request JSON or stored evidence. */
export function Localized({ children }: { children: ReactNode }) {
  return <>{textChildren(children, useContext(LanguageContext))}</>;
}

export function LocalizedAttributes({ children }: { children: ReactElement }) {
  const locale = useContext(LanguageContext);
  if (!isValidElement(children)) return children;
  const props = children.props as Record<string, unknown>;
  const translated: Record<string, unknown> = {};
  for (const name of ['placeholder', 'title', 'aria-label', 'alt']) {
    if (typeof props[name] === 'string') translated[name] = translateText(props[name], locale);
  }
  return cloneElement(children, translated);
}
