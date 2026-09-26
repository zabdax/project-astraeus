"use client";

/**
 * Cinematic 3D transit hero (react-three-fiber, lazy + client-only).
 *
 * A limb-glowing star, an inclined orbit ring, and a planet that plays
 * along it.  When the planet crosses the stellar disc a transit flag
 * fires to the HTML overlay.  Pure illustration of geometry -- labelled
 * as such, never data.  Static frame under prefers-reduced-motion,
 * pointer parallax otherwise, DPR capped at 2.
 */
import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

const ORBIT_R = 2.3;
const STAR_R = 1;

function StarfieldPoints({ count = 700 }: { count?: number }) {
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 14 + Math.random() * 22;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.cos(phi) * 0.6;
      arr[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
    }
    return arr;
  }, [count]);
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial size={0.055} color="#a9c0e8" sizeAttenuation transparent opacity={0.8} />
    </points>
  );
}

function Star() {
  return (
    <group>
      {/* halo shells (additive, cheap) */}
      <mesh>
        <sphereGeometry args={[STAR_R * 1.55, 32, 32]} />
        <meshBasicMaterial color="#e8c46a" transparent opacity={0.1} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[STAR_R * 1.22, 32, 32]} />
        <meshBasicMaterial color="#f4d98c" transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      {/* limb-darkened-look disc: bright core material + dark rim via fresnel-ish layering */}
      <mesh>
        <sphereGeometry args={[STAR_R, 48, 48]} />
        <meshBasicMaterial color="#f7e3ac" />
      </mesh>
      <mesh scale={1.002}>
        <sphereGeometry args={[STAR_R, 48, 48]} />
        <meshBasicMaterial color="#8a6a35" transparent opacity={0.35} blending={THREE.MultiplyBlending} depthWrite={false} />
      </mesh>
      <pointLight intensity={2.2} distance={0} decay={0} color="#fff3d0" />
    </group>
  );
}

function OrbitRing() {
  const geometry = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= 180; i++) {
      const a = (i / 180) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * ORBIT_R, Math.sin(a) * ORBIT_R * 0.18, Math.sin(a) * ORBIT_R * 0.98));
    }
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, []);
  return (
    <lineLoop geometry={geometry}>
      <lineBasicMaterial color="#6cb0ff" transparent opacity={0.45} />
    </lineLoop>
  );
}

function Planet({ onTransit }: { onTransit: (inTransit: boolean, phase: number) => void }) {
  const ref = useRef<THREE.Mesh>(null);
  const glow = useRef<THREE.Mesh>(null);
  const last = useRef<boolean | null>(null);
  useFrame(({ clock }) => {
    const a = clock.elapsedTime * 0.28;
    const x = Math.cos(a) * ORBIT_R;
    const y = Math.sin(a) * ORBIT_R * 0.18;
    const z = Math.sin(a) * ORBIT_R * 0.98;
    ref.current?.position.set(x, y, z);
    glow.current?.position.set(x, y, z);
    const inTransit = z > 0 && Math.hypot(x, y) < STAR_R * 1.02;
    if (inTransit !== last.current) {
      last.current = inTransit;
      onTransit(inTransit, ((a / (Math.PI * 2)) % 1 + 1) % 1);
    }
  });
  return (
    <group>
      <mesh ref={glow}>
        <sphereGeometry args={[0.2, 16, 16]} />
        <meshBasicMaterial color="#6cb0ff" transparent opacity={0.3} blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <mesh ref={ref}>
        <sphereGeometry args={[0.11, 32, 32]} />
        <meshStandardMaterial color="#9fc2ee" roughness={0.55} metalness={0.15} />
      </mesh>
    </group>
  );
}

function CameraRig() {
  useFrame(({ camera, pointer }) => {
    camera.position.x += (pointer.x * 0.7 - camera.position.x) * 0.04;
    camera.position.y += (1.35 + pointer.y * 0.45 - camera.position.y) * 0.04;
    camera.lookAt(0, 0, 0);
  });
  return null;
}

export default function TransitHero() {
  const reduced = useMemo(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );
  const [transit, setTransit] = useState(false);
  const [phase, setPhase] = useState(0);

  return (
    <div className="hero3d">
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 1.35, 5.4], fov: 42 }}
        frameloop={reduced ? "never" : "always"}
        gl={{ antialias: true, alpha: true }}
        aria-hidden
      >
        <StarfieldPoints />
        <Star />
        <OrbitRing />
        <Planet
          onTransit={(t, p) => {
            setTransit(t);
            setPhase(p);
          }}
        />
        {!reduced && <CameraRig />}
      </Canvas>
      <div className="hero3d-chip glass">
        <span className={`status-dot ${transit ? "completed" : "running"}`} />
        <span className="mono">{transit ? "TRANSIT — planet on disc" : `orbital phase ${(phase * 100).toFixed(1)}%`}</span>
        <span className="muted">illustration of geometry, not data</span>
      </div>
    </div>
  );
}
