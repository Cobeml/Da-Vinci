"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Bounds, Center, Grid, OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";

function Mount({ url, mounted, ready }: { url: string; mounted: boolean; ready: () => void }) {
  const { scene } = useGLTF(url);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.material = new THREE.MeshStandardMaterial({
          color: "#c76a36", metalness: .15, roughness: .48,
          emissive: "#a1400e", emissiveIntensity: mounted ? .18 : .025,
        });
      }
    });
    return clone;
  }, [scene, mounted]);
  useEffect(() => { ready(); }, [model, ready]);
  useEffect(() => () => {
    model.traverse((object) => {
      if (object instanceof THREE.Mesh) (object.material as THREE.Material).dispose();
    });
  }, [model]);
  return mounted
    ? <group position={[190, 26, 0]} rotation={[Math.PI, 0, 0]}><primitive object={model} /></group>
    : <primitive object={model} />;
}

function VTOL() {
  const wing = useMemo(() => {
    const shape = new THREE.Shape();
    const points = [[-120, -700], [-30, -700], [80, -90], [80, 90], [-30, 700], [-120, 700], [-170, 90], [-170, -90]];
    points.forEach(([x, z], i) => i ? shape.lineTo(x, z) : shape.moveTo(x, z));
    shape.closePath();
    return new THREE.ExtrudeGeometry(shape, { depth: 12, bevelEnabled: true, bevelSize: 2, bevelThickness: 2, bevelSegments: 2 });
  }, []);
  useEffect(() => () => wing.dispose(), [wing]);
  return <group>
    <mesh position={[-65, 75, 0]} scale={[365, 58, 70]}>
      <sphereGeometry args={[1, 48, 24]} /><meshStandardMaterial color="#dce0da" roughness={.62} />
    </mesh>
    <mesh position={[55, 119, 0]} scale={[110, 19, 47]}>
      <sphereGeometry args={[1, 32, 16]} /><meshStandardMaterial color="#536361" metalness={.25} roughness={.4} />
    </mesh>
    <mesh geometry={wing} position={[0, 99, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <meshStandardMaterial color="#d4d9d1" roughness={.6} />
    </mesh>
    {[-300, 300].map((z) => <group key={z}>
      <mesh position={[-55, 98, z]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[9, 9, 650, 14]} /><meshStandardMaterial color="#47504b" roughness={.55} />
      </mesh>
      {[-300, 225].map((x) => <group key={x} position={[x, 112, z]}>
        <mesh><cylinderGeometry args={[20, 17, 30, 24]} /><meshStandardMaterial color="#515d55" metalness={.4} roughness={.45} /></mesh>
        <mesh position={[0, 18, 0]} rotation={[0, z < 0 ? .3 : -.3, 0]}>
          <boxGeometry args={[235, 4, 15]} /><meshStandardMaterial color="#343f38" roughness={.55} />
        </mesh>
        <mesh position={[0, 23, 0]}><sphereGeometry args={[12, 16, 8]} /><meshStandardMaterial color="#a3aca3" /></mesh>
      </group>)}
    </group>)}
    <mesh position={[-360, 95, 0]}><boxGeometry args={[95, 9, 520]} /><meshStandardMaterial color="#d4d9d1" /></mesh>
    {[-205, 205].map(z => <mesh key={z} position={[-370, 145, z]} rotation={[0, 0, -.22]}>
      <boxGeometry args={[75, 100, 8]} /><meshStandardMaterial color="#bac5b8" />
    </mesh>)}
    <mesh position={[190, 30, 0]}><boxGeometry args={[108, 8, 78]} /><meshStandardMaterial color="#747f74" /></mesh>
    <mesh position={[190, -9, 0]} scale={[16, 16, 23]}><sphereGeometry args={[1, 24, 16]} /><meshStandardMaterial color="#535e58" /></mesh>
    <mesh position={[208, -9, 0]} rotation={[0, 0, -Math.PI / 2]}>
      <cylinderGeometry args={[10, 12, 12, 24]} /><meshStandardMaterial color="#182b2c" metalness={.5} roughness={.22} />
    </mesh>
  </group>;
}

export default function SensorViewer({ url, mounted, reset }: { url: string; mounted: boolean; reset: number }) {
  const [loaded, setLoaded] = useState(false);
  // Separate scenes fit their own bounds; no shared camera state between cards.
  return <div data-testid="sensor-canvas" data-loaded={loaded} data-mounted={mounted} style={{ width: "100%", height: "100%" }}>
    <Canvas key={`${mounted}-${reset}`} frameloop="demand" camera={{ position: mounted ? [950, 650, 1050] : [145, 105, 145], fov: 36, near: .1, far: 10000 }} gl={{ antialias: true, preserveDrawingBuffer: true }}>
      <color attach="background" args={["#edf0ea"]} />
      <ambientLight intensity={1.4} />
      <hemisphereLight args={["#ffffff", "#b5bdac", 1.2]} />
      <directionalLight position={[200, 300, 180]} intensity={2.7} />
      <directionalLight position={[-200, 120, -180]} intensity={1.1} color="#e3eee4" />
      <Suspense fallback={null}>
        <Bounds fit clip observe margin={mounted ? 1.15 : 1.45} maxDuration={.4}>
          <Center>
            {mounted && <VTOL />}
            <Mount url={url} mounted={mounted} ready={() => setLoaded(true)} />
          </Center>
        </Bounds>
      </Suspense>
      {!mounted && <Grid position={[0, -25, 0]} args={[400, 400]} cellSize={10} sectionSize={50} cellColor="#d9dfd3" sectionColor="#c7d1c1" cellThickness={.4} sectionThickness={.65} fadeDistance={600} />}
      <OrbitControls makeDefault enableDamping minDistance={mounted ? 180 : 55} maxDistance={mounted ? 5000 : 650} />
    </Canvas>
  </div>;
}
