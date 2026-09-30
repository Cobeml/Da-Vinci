"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import {
  Bounds,
  Center,
  Grid,
  OrbitControls,
  useGLTF,
} from "@react-three/drei";
import * as THREE from "three";
import DroneReference from "./DroneReference";

function Mount({
  url,
  mounted,
  ready,
}: {
  url: string;
  mounted: boolean;
  ready: () => void;
}) {
  const { scene } = useGLTF(url);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.material = new THREE.MeshStandardMaterial({
          color: "#c76a36",
          metalness: 0.15,
          roughness: 0.48,
          emissive: "#a1400e",
          emissiveIntensity: mounted ? 0.18 : 0.025,
        });
      }
    });
    return clone;
  }, [scene, mounted]);
  useEffect(() => {
    ready();
  }, [model, ready]);
  useEffect(
    () => () => {
      model.traverse((object) => {
        if (object instanceof THREE.Mesh)
          (object.material as THREE.Material).dispose();
      });
    },
    [model],
  );
  return mounted ? (
    <group position={[190, 26, 0]} rotation={[Math.PI, 0, 0]}>
      <primitive object={model} />
    </group>
  ) : (
    <primitive object={model} />
  );
}

export default function SensorViewer({
  url,
  mounted,
  reset,
}: {
  url: string;
  mounted: boolean;
  reset: number;
}) {
  const [loaded, setLoaded] = useState(false);
  // Separate scenes fit their own bounds; no shared camera state between cards.
  return (
    <div
      data-testid="sensor-canvas"
      data-loaded={loaded}
      data-mounted={mounted}
      style={{ width: "100%", height: "100%" }}
    >
      <Canvas
        key={`${mounted}-${reset}`}
        frameloop="demand"
        camera={{
          position: mounted ? [950, 650, 1050] : [145, 105, 145],
          fov: 36,
          near: 0.1,
          far: 10000,
        }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
      >
        <color attach="background" args={["#edf0ea"]} />
        <ambientLight intensity={1.4} />
        <hemisphereLight args={["#ffffff", "#b5bdac", 1.2]} />
        <directionalLight position={[200, 300, 180]} intensity={2.7} />
        <directionalLight
          position={[-200, 120, -180]}
          intensity={1.1}
          color="#e3eee4"
        />
        <Suspense fallback={null}>
          <Bounds
            fit
            clip
            observe
            margin={mounted ? 1.15 : 1.45}
            maxDuration={0.4}
          >
            <Center>
              {mounted && <DroneReference />}
              <Mount
                url={url}
                mounted={mounted}
                ready={() => setLoaded(true)}
              />
            </Center>
          </Bounds>
        </Suspense>
        {!mounted && (
          <Grid
            position={[0, -25, 0]}
            args={[400, 400]}
            cellSize={10}
            sectionSize={50}
            cellColor="#d9dfd3"
            sectionColor="#c7d1c1"
            cellThickness={0.4}
            sectionThickness={0.65}
            fadeDistance={600}
          />
        )}
        <OrbitControls
          makeDefault
          enableDamping
          minDistance={mounted ? 180 : 55}
          maxDistance={mounted ? 5000 : 650}
        />
      </Canvas>
    </div>
  );
}
