(() => {
  const status = document.getElementById('offline-status');
  const showNetwork = () => { if (status) status.hidden = navigator.onLine; };
  window.addEventListener('online', showNetwork); window.addEventListener('offline', showNetwork); showNetwork();
  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  const locate = document.getElementById('locate');
  if (locate) locate.addEventListener('click', () => {
    const help = document.getElementById('location-help');
    if (!navigator.geolocation) { help.textContent = 'Location is not available. Enter a landmark or locality instead.'; return; }
    locate.disabled = true; locate.textContent = 'Finding location…';
    navigator.geolocation.getCurrentPosition(({coords}) => {
      document.getElementById('latitude').value = coords.latitude.toFixed(6); document.getElementById('longitude').value = coords.longitude.toFixed(6);
      help.textContent = 'Location coordinates added. You may still enter a landmark.'; locate.disabled = false; locate.textContent = 'Update location';
    }, () => { help.textContent = 'Location permission was not granted. Enter a landmark or locality instead.'; locate.disabled = false; locate.textContent = 'Try location again'; }, {timeout:8000, maximumAge:60000});
  });
  const form = document.getElementById('sos-form');
  if (form) form.addEventListener('submit', event => {
    if (!navigator.onLine) { event.preventDefault(); alert('You are offline. This request has not been sent. Reconnect and submit it again.'); return; }
    const button = document.getElementById('submit-sos'); button.disabled = true; button.textContent = 'Submitting…';
  });
})();
