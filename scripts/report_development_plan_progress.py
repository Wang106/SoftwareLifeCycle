"""Render the seven plan progress rows from fixed acceptance milestones."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = '<!-- development-plan-progress:start -->'
END = '<!-- development-plan-progress:end -->'


def render(ledger):
    lines = ['| 计划 | 已完成 / 验收里程碑 | 完成度 |',
             '| --- | ---: | ---: |']
    for group in ledger['groups']:
        milestones = group['milestones']
        completed = sum(item['complete'] for item in milestones)
        percent = round(completed * 100 / len(milestones))
        lines.append(f"| {group['id']}. {group['name']} | {completed}/{len(milestones)} | **{percent}%** |")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--update', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    ledger = json.loads((ROOT/'docs/development-plan-progress.json').read_text())
    table = render(ledger)
    path = ROOT/'docs/development-plan.md'
    document = path.read_text()
    if args.update or args.check:
        before, separator, rest = document.partition(START)
        current, closing, after = rest.partition(END)
        if not separator or not closing:
            parser.error('Progress markers missing from development-plan.md')
        if args.check:
            if current.strip() != table:
                parser.exit(1, 'Development plan progress table is stale; run --update.\n')
            return
        path.write_text(before+START+'\n'+table+'\n'+END+after)
    else:
        print(table)


if __name__ == '__main__':
    main()
