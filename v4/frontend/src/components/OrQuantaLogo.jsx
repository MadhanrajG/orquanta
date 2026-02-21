import React, { useState } from 'react';

/**
 * OrQuantaLogo — SVG Logo Component
 * ===================================
 * Stylized OQ monogram with quantum orbit ring.
 * Gradient: Quantum Blue (#00D4FF) → Deep Purple (#7B2FFF)
 *
 * Props:
 *   size      — 'sm'|'md'|'lg'|'xl' (default: 'md')
 *   variant   — 'full'|'icon'|'wordmark' (default: 'full')
 *   animated  — bool: pulse on hover (default: true)
 *   className — extra CSS classes
 *   style     — inline style override
 *
 * Usage:
 *   <OrQuantaLogo />
 *   <OrQuantaLogo size="lg" variant="icon" />
 *   <OrQuantaLogo size="xl" variant="full" animated={false} />
 */

const SIZES = {
    sm: { icon: 28, fontSize: '1rem', letterSpacing: '0.02em' },
    md: { icon: 40, fontSize: '1.375rem', letterSpacing: '0.02em' },
    lg: { icon: 56, fontSize: '1.875rem', letterSpacing: '0.02em' },
    xl: { icon: 80, fontSize: '2.5rem', letterSpacing: '0.02em' },
};

const GRADIENT_ID_PREFIX = 'orquanta-logo-grad';
let instanceId = 0;

const OrQuantaLogo = ({
    size = 'md',
    variant = 'full',
    animated = true,
    className = '',
    style = {},
}) => {
    const [hovered, setHovered] = useState(false);
    const { icon: iconSize, fontSize, letterSpacing } = SIZES[size] || SIZES.md;
    const gradId = `${GRADIENT_ID_PREFIX}-${React.useId ? React.useId() : ++instanceId}`;

    const pulseStyle = animated && hovered
        ? { filter: 'drop-shadow(0 0 12px rgba(0, 212, 255, 0.6))' }
        : { filter: 'drop-shadow(0 0 4px rgba(0, 212, 255, 0.2))' };

    const orbitStyle = {
        transition: animated ? 'transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)' : 'none',
        transformOrigin: '50% 50%',
        transform: hovered ? 'rotate(30deg) scale(1.05)' : 'rotate(0deg) scale(1)',
    };

    const OQIcon = () => (
        <svg
            width={iconSize}
            height={iconSize}
            viewBox="0 0 80 80"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            style={{ ...pulseStyle, transition: 'filter 0.3s ease', flexShrink: 0 }}
            aria-label="OrQuanta logo"
        >
            <defs>
                {/* Primary gradient: Quantum Blue → Deep Purple */}
                <linearGradient id={`${gradId}-main`} x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#00D4FF" />
                    <stop offset="100%" stopColor="#7B2FFF" />
                </linearGradient>
                {/* Orbit ring gradient */}
                <linearGradient id={`${gradId}-ring`} x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#00D4FF" stopOpacity="0.8" />
                    <stop offset="50%" stopColor="#7B2FFF" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#00D4FF" stopOpacity="0.1" />
                </linearGradient>
                {/* Background circle gradient */}
                <radialGradient id={`${gradId}-bg`} cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#0F1624" />
                    <stop offset="100%" stopColor="#0A0B14" />
                </radialGradient>
                {/* Glow filter */}
                <filter id={`${gradId}-glow`} x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="2.5" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
            </defs>

            {/* Background circle */}
            <circle cx="40" cy="40" r="38" fill={`url(#${gradId}-bg)`} stroke="#1E2A3A" strokeWidth="1" />

            {/* Quantum orbit ring */}
            <g style={orbitStyle}>
                <ellipse
                    cx="40" cy="40" rx="32" ry="14"
                    stroke={`url(#${gradId}-ring)`}
                    strokeWidth="1.5"
                    fill="none"
                    transform="rotate(-30 40 40)"
                    filter={`url(#${gradId}-glow)`}
                />
                {/* Orbit dot — represents quantum particle */}
                <circle
                    cx="62" cy="34"
                    r="3"
                    fill="#00D4FF"
                    opacity="0.9"
                    filter={`url(#${gradId}-glow)`}
                />
            </g>

            {/* OQ Monogram */}
            {/* "O" — outer ring with inner negative space */}
            <circle
                cx="32" cy="40" r="13"
                stroke={`url(#${gradId}-main)`}
                strokeWidth="5"
                fill="none"
                filter={`url(#${gradId}-glow)`}
            />
            {/* "O" lower-right notch (makes it distinctive) */}
            <line
                x1="41" y1="49"
                x2="46" y2="54"
                stroke={`url(#${gradId}-main)`}
                strokeWidth="5"
                strokeLinecap="round"
            />

            {/* "Q" — vertical bar and curve */}
            <path
                d="M50 27 L50 47 Q50 54 57 54 Q64 54 64 47 L64 34 Q64 27 57 27 Z"
                fill="none"
                stroke={`url(#${gradId}-main)`}
                strokeWidth="4.5"
                strokeLinejoin="round"
                filter={`url(#${gradId}-glow)`}
            />
            {/* "Q" diagonal tail */}
            <line
                x1="60" y1="50"
                x2="67" y2="57"
                stroke={`url(#${gradId}-main)`}
                strokeWidth="4.5"
                strokeLinecap="round"
            />
        </svg>
    );

    const wordmarkStyles = {
        display: 'flex',
        alignItems: 'center',
        gap: iconSize * 0.3 + 'px',
        cursor: 'default',
        userSelect: 'none',
        textDecoration: 'none',
        ...style,
    };

    const textStyles = {
        fontFamily: "'Space Grotesk', 'Inter', sans-serif",
        fontWeight: 700,
        fontSize,
        letterSpacing,
        background: 'linear-gradient(135deg, #00D4FF 0%, #7B2FFF 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
        lineHeight: 1,
        transition: animated ? 'filter 0.3s ease' : 'none',
        filter: hovered && animated ? 'brightness(1.15)' : 'brightness(1)',
    };

    if (variant === 'icon') {
        return (
            <div
                className={className}
                style={{ display: 'inline-flex', ...style }}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
                role="img"
                aria-label="OrQuanta"
            >
                <OQIcon />
            </div>
        );
    }

    if (variant === 'wordmark') {
        return (
            <div
                className={className}
                style={wordmarkStyles}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
            >
                <span style={textStyles}>OrQuanta</span>
            </div>
        );
    }

    // Default: 'full' — icon + wordmark
    return (
        <div
            className={className}
            style={wordmarkStyles}
            onMouseEnter={() => setHovered(true)}
            onMouseLeave={() => setHovered(false)}
            role="img"
            aria-label="OrQuanta"
        >
            <OQIcon />
            <span style={textStyles}>OrQuanta</span>
        </div>
    );
};

export default OrQuantaLogo;

// ─── Named size exports for convenience ──────────────────────────────────────

export const OrQuantaLogoSm = (props) => <OrQuantaLogo size="sm" {...props} />;
export const OrQuantaLogoMd = (props) => <OrQuantaLogo size="md" {...props} />;
export const OrQuantaLogoLg = (props) => <OrQuantaLogo size="lg" {...props} />;
export const OrQuantaLogoXl = (props) => <OrQuantaLogo size="xl" {...props} />;
