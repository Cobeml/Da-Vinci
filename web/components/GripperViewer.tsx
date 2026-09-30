"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Bounds, Center, OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";
import DroneReference from "./DroneReference";

type Parameters = { depth_mm: number; nodes: number[][]; edges: number[][] };
type Props = {
  assets: Record<string, string>;
  parameters: Parameters;
  gap: number;
  frame: boolean;
  stresses: number[];
  mounted?: boolean;
};

function Part({
  url,
  shift,
  ghost,
  ready,
}: {
  url: string;
  shift: number;
  ghost: boolean;
  ready: () => void;
}) {
  const { scene } = useGLTF(url);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        const original = object.material as THREE.MeshStandardMaterial;
        object.material = new THREE.MeshStandardMaterial({
          color: original.color,
          metalness: 0.22,
          roughness: 0.48,
          transparent: ghost,
          opacity: ghost ? 0.17 : 1,
          depthWrite: !ghost,
        });
      }
    });
    return clone;
  }, [scene, ghost]);
  useEffect(() => {
    ready();
  }, [model, ready]);
  useEffect(
    () => () => {
      model.traverse((object) => {
        if (object instanceof THREE.Mesh) object.material.dispose();
      });
    },
    [model],
  );
  return (
    <group position={[shift, 0, 0]}>
      <primitive object={model} />
    </group>
  );
}

function Beam({
  a,
  b,
  width,
  stress,
}: {
  a: number[];
  b: number[];
  width: number;
  stress: number;
}) {
  const start = new THREE.Vector3(...a),
    end = new THREE.Vector3(...b);
  const delta = end.clone().sub(start),
    midpoint = start.clone().add(end).multiplyScalar(0.5);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    delta.clone().normalize(),
  );
  const color = new THREE.Color().setHSL(
    0.32 * (1 - Math.min(stress / 80, 1)),
    0.65,
    0.44,
  );
  return (
    <mesh position={midpoint} quaternion={quaternion}>
      <cylinderGeometry args={[width / 3, width / 3, delta.length(), 12]} />
      <meshStandardMaterial color={color} roughness={0.55} />
    </mesh>
  );
}

export default function GripperViewer({
  assets,
  parameters,
  gap,
  frame,
  stresses,
  mounted = false,
}: Props) {
  const [loaded, setLoaded] = useState(false);
  return (
    <div
      data-testid="gripper-canvas"
      data-loaded={loaded}
      data-gap={gap}
      data-frame={frame}
      data-mounted={mounted}
      style={{ width: "100%", height: "100%" }}
    >
      <Canvas
        key={String(mounted)}
        frameloop="demand"
        camera={{
          position: mounted ? [950, 450, 1050] : [230, 165, 245],
          fov: 36,
          near: 0.1,
          far: 10000,
        }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
      >
        <color attach="background" args={["#edf0ea"]} />
        <ambientLight intensity={1.5} />
        <hemisphereLight args={["#fff", "#b5bdac", 1.2]} />
        <directionalLight position={[150, 250, 160]} intensity={2.4} />
        <directionalLight position={[-150, 80, -100]} intensity={1} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.25} maxDuration={0.4}>
            <Center>
              {mounted && (
                <>
                  <DroneReference sensor={false} />
                  <mesh position={[30, 15, 0]}>
                    <boxGeometry args={[220, 10, 80]} />
                    <meshStandardMaterial color="#747f74" />
                  </mesh>
                  {[-40, 100].map((x) => (
                    <mesh key={x} position={[x, 29, 0]}>
                      <boxGeometry args={[12, 24, 52]} />
                      <meshStandardMaterial color="#747f74" />
                    </mesh>
                  ))}
                </>
              )}
              <group
                position={mounted ? [30, 10, 0] : [0, 0, 0]}
                rotation={mounted ? [Math.PI, 0, 0] : [0, 0, 0]}
              >
                <Part
                  url={assets["base.glb"]}
                  shift={0}
                  ghost={false}
                  ready={() => {}}
                />
                <Part
                  url={assets["right.glb"]}
                  shift={(gap - 60) / 2}
                  ghost={frame}
                  ready={() => {}}
                />
                <Part
                  url={assets["left.glb"]}
                  shift={-(gap - 60) / 2}
                  ghost={frame}
                  ready={() => setLoaded(true)}
                />
                {frame &&
                  [-1, 1].flatMap((sign) =>
                    parameters.edges.map(([a, b, width], index) => (
                      <Beam
                        key={`${sign}-${index}`}
                        a={[
                          sign * (gap / 2 + parameters.nodes[a][0]),
                          18.3 + parameters.nodes[a][1],
                          0,
                        ]}
                        b={[
                          sign * (gap / 2 + parameters.nodes[b][0]),
                          18.3 + parameters.nodes[b][1],
                          0,
                        ]}
                        width={width}
                        stress={stresses[index] || 0}
                      />
                    )),
                  )}
              </group>
            </Center>
          </Bounds>
        </Suspense>
        <OrbitControls
          makeDefault
          enableDamping
          minDistance={mounted ? 180 : 100}
          maxDistance={mounted ? 5000 : 1200}
        />
      </Canvas>
    </div>
  );
}
