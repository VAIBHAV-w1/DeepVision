(function () {
  try {
    var urlParams = new URLSearchParams(window.location.search);
    var urlTheme = urlParams.get('theme');
    var pref = (urlTheme && (urlTheme === 'light' || urlTheme === 'dark' || urlTheme === 'system'))
      ? urlTheme
      : (localStorage.getItem('deepvision_theme') || 'dark');
    var resolved = pref;
    if (pref === 'system') {
      resolved = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', resolved);
    document.documentElement.setAttribute('data-theme-pref', pref);
  } catch (e) {}
})();
