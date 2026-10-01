import chinese from './i18n/zh.json';
import templates from './i18n/templates.json';

export type Locale = 'zh' | 'en';
export function resolveLocale(value: unknown): Locale { return value === 'en' ? 'en' : 'zh'; }
const dictionary: Record<string, string> = chinese;
const normalize = (text: string) => text.replace(/\s+/g, ' ').trim();
const patterns = Object.entries(templates).map(([source, target]) => {
  const parts = source.split(/(\{\d+\})/);
  const indexes: number[] = [];
  const pattern = parts.map(part => {
    if (/^\{\d+\}$/.test(part)) { indexes.push(Number(part.slice(1, -1))); return '(.+?)'; }
    return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }).join('');
  return { regex: new RegExp('^'+pattern+'$'), target, indexes };
});

export function translateText(text: string, locale: Locale): string {
  if (locale === 'en' || !text.trim()) return text;
  const key = normalize(text);
  let result = dictionary[key];
  if (result === undefined && key.includes(' · ')) {
    const parts = key.split(' · ');
    const translated = parts.map(part => translateText(part, locale));
    if (translated.some((part, index) => part !== parts[index])) result = translated.join(' · ');
  }
  if (result === undefined) {
    for (const { regex, target, indexes } of patterns) {
      const match = key.match(regex);
      if (match) {
        result = target.replace(/\{(\d+)\}/g, (_, index) => {
          const raw = match[indexes.indexOf(Number(index))+1];
          return dictionary[normalize(raw)] ?? raw;
        });
        break;
      }
    }
  }
  if (result === undefined) return text; // User evidence/identifiers have no invented translation.
  return (text.match(/^\s*/)?.[0] ?? '') + result + (text.match(/\s*$/)?.[0] ?? '');
}
