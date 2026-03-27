// src/components/common/Logo.jsx
export default function Logo() {
  return (
    <div className="logo">
      <img
        src="/logo.png"
        alt="cHATBOX"
        style={{
          width: '34px',
          height: '34px',
          borderRadius: 'var(--radius)',
          objectFit: 'cover',
          flexShrink: 0,
        }}
      />
      <span className="logo-text">cHATBOX</span>
    </div>
  );
}
