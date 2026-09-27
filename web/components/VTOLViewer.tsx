"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Bounds, Center, OrbitControls, useGLTF } from "@react-three/drei";
import * as THREE from "three";

function Aircraft({ url, ready, internal }: { url: string; ready: () => void; internal: boolean }) {
  const { scene } = useGLTF(url);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.traverse(o => {
      if (internal && /^(wing|tail)-?1$/.test(o.name)) o.visible = false;
      if (internal && o.name.includes("fairing")) o.visible = false;
      if (o instanceof THREE.Mesh) {
        const original = o.material as THREE.MeshStandardMaterial;
        o.material = new THREE.MeshStandardMaterial({ color: original.color, metalness: .15, roughness: .6 });
      }
    });
    return clone;
  }, [scene, internal]);
  useEffect(() => { ready(); }, [model, ready]);
  useEffect(() => () => { model.traverse(o => { if (o instanceof THREE.Mesh) o.material.dispose(); }); }, [model]);
  return <primitive object={model} />;
}
export default function VTOLViewer({ url, internal = false }: { url: string; internal?: boolean }) {
  const [loaded, setLoaded] = useState(false);
  return <div data-testid="vtol-canvas" data-loaded={loaded} style={{ width: "100%", height: "100%" }}>
    <Canvas frameloop="demand" camera={{ position: [-1700, 1600, 2100], fov: 36, near: 1, far: 15000 }} gl={{ antialias: true, preserveDrawingBuffer: true }}>
      <color attach="background" args={["#edf0ea"]} />
      <ambientLight intensity={1.5} /><hemisphereLight args={["#fff", "#b5bdac", 1.2]} />
      <directionalLight position={[-1000, 2500, 1600]} intensity={2.4} />
      <directionalLight position={[1000, 800, -1000]} intensity={1} />
      <Suspense fallback={null}><Bounds fit clip observe margin={.95} maxDuration={.3}><Center><Aircraft url={url} internal={internal} ready={() => setLoaded(true)} /></Center></Bounds></Suspense>
      <OrbitControls makeDefault enableDamping minDistance={700} maxDistance={7000} />
    </Canvas>
  </div>;
}
