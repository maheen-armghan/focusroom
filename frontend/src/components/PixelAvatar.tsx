import { useMemo } from "react";

export type AvatarConfig = {
  hair: "short" | "long" | "buzz" | "bun";
  skin: string;
  outfit: "hoodie" | "tee" | "sweater" | "blazer";
  accessory: "none" | "glasses" | "headphones" | "beanie";
  color: string; // outfit color
};

export const DEFAULT_AVATAR: AvatarConfig = {
  hair: "short", skin: "#f5d6b8", outfit: "hoodie", accessory: "none", color: "#7c9eff",
};

export function PixelAvatar({ config = DEFAULT_AVATAR, size = 96 }: { config?: AvatarConfig; size?: number }) {
  const c = useMemo(() => ({ ...DEFAULT_AVATAR, ...config }), [config]);
  const hairColor = "#3a2a1f";
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} shapeRendering="crispEdges" style={{ imageRendering: "pixelated" }}>
      {/* Body / outfit */}
      <rect x="4" y="10" width="8" height="6" fill={c.color} />
      <rect x="3" y="11" width="1" height="4" fill={c.color} />
      <rect x="12" y="11" width="1" height="4" fill={c.color} />
      {c.outfit === "blazer" && <rect x="7" y="10" width="2" height="6" fill="#1a1a1a" />}
      {c.outfit === "sweater" && <rect x="4" y="11" width="8" height="1" fill="#fff" opacity="0.25" />}
      {/* Neck */}
      <rect x="7" y="9" width="2" height="1" fill={c.skin} />
      {/* Head */}
      <rect x="5" y="4" width="6" height="6" fill={c.skin} />
      {/* Eyes */}
      <rect x="6" y="6" width="1" height="1" fill="#1a1a1a" />
      <rect x="9" y="6" width="1" height="1" fill="#1a1a1a" />
      {/* Mouth */}
      <rect x="7" y="8" width="2" height="1" fill="#a04030" />
      {/* Hair */}
      {c.hair === "short" && <rect x="5" y="3" width="6" height="2" fill={hairColor} />}
      {c.hair === "buzz" && <rect x="5" y="4" width="6" height="1" fill={hairColor} />}
      {c.hair === "long" && (<>
        <rect x="5" y="3" width="6" height="2" fill={hairColor} />
        <rect x="4" y="5" width="1" height="5" fill={hairColor} />
        <rect x="11" y="5" width="1" height="5" fill={hairColor} />
      </>)}
      {c.hair === "bun" && (<>
        <rect x="5" y="3" width="6" height="2" fill={hairColor} />
        <rect x="7" y="2" width="2" height="1" fill={hairColor} />
      </>)}
      {/* Accessory */}
      {c.accessory === "glasses" && (<>
        <rect x="6" y="6" width="1" height="1" fill="#1a1a1a" stroke="#1a1a1a" />
        <rect x="9" y="6" width="1" height="1" fill="#1a1a1a" stroke="#1a1a1a" />
        <rect x="7" y="6" width="2" height="1" fill="#1a1a1a" opacity="0.3" />
      </>)}
      {c.accessory === "headphones" && (<>
        <rect x="4" y="5" width="1" height="3" fill="#222" />
        <rect x="11" y="5" width="1" height="3" fill="#222" />
        <rect x="5" y="3" width="6" height="1" fill="#222" />
      </>)}
      {c.accessory === "beanie" && <rect x="4" y="3" width="8" height="2" fill="#c44" />}
    </svg>
  );
}
