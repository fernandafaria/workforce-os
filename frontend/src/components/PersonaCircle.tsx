interface PersonaCircleProps {
  name: string;
  initials?: string;
  size?: number;
  fontSize?: number;
  color1?: string;
  color2?: string;
}

function getInitials(name: string, fallback?: string): string {
  if (fallback) return fallback;
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

export function PersonaCircle({ name, initials, size = 36, fontSize = 14, color1 = '#1A4D5C', color2 = '#6E6E73' }: PersonaCircleProps) {
  return (
    <span
      style={{
        width: size, height: size, borderRadius: size > 40 ? 14 : 10,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flex: '0 0 auto',
        background: `linear-gradient(135deg, ${color1}, ${color2})`,
        color: '#fff', fontSize, fontWeight: 600,
      }}
    >
      {getInitials(name, initials)}
    </span>
  );
}
