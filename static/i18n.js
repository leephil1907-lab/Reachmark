/* Locale strings for JS. T(key, englishDefault) renders the translated string
   once loaded, else the inline English default — never a raw key. i18nReady
   resolves when strings arrive (immediately for English); initial data loads
   should wait for it so first paint is already translated. */
var RM_STRINGS = {};
function T(key, fb) { return RM_STRINGS[key] || fb || key; }
var i18nReady = (function () {
  var lang = (document.documentElement.lang || 'en').slice(0, 2);
  if (lang === 'en') return Promise.resolve({});
  return fetch('/static/locales/' + lang + '.json').then(function (r) {
    if (!r.ok) throw new Error('locale ' + lang);
    return r.json();
  }).then(function (j) { RM_STRINGS = j || {}; return RM_STRINGS; }).catch(function () { return {}; });
})();
function setLocale(code) {
  try {
    document.cookie = 'rm_locale=' + code + ';max-age=31536000;path=/;SameSite=Lax';
    localStorage.setItem('rm_locale', code);
  } catch (e) {}
  location.reload();
}
