import { useState, useEffect } from 'react';

export default function LocalTime({ timezone }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    if (!timezone) return;
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, [timezone]);

  if (!timezone) return 'Not specified';

  try {
    return now.toLocaleTimeString('en-US', {
      timeZone: timezone,
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
      timeZoneName: 'short',
    });
  } catch {
    return 'Not specified';
  }
}
