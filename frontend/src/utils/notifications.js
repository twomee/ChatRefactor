let permissionGranted = false;

export async function requestNotificationPermission() {
  if (!('Notification' in globalThis)) return false;
  if (Notification.permission === 'granted') {
    permissionGranted = true;
    return true;
  }
  if (Notification.permission === 'denied') return false;
  const result = await Notification.requestPermission();
  permissionGranted = result === 'granted';
  return permissionGranted;
}

export function sendBrowserNotification(title, body, onClick) {
  if (!permissionGranted || document.hasFocus()) return;
  const notification = new Notification(title, {
    body,
    icon: '/favicon.ico',
    tag: 'chatbox-mention',
  });
  if (onClick) {
    notification.onclick = () => {
      window.focus();
      onClick();
      notification.close();
    };
  }
  setTimeout(() => notification.close(), 5000);
}
