"use client";
import { Suspense, useEffect, useMemo, memo } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import {
  Grid,
  OrbitControls,
  useGLTF,
  Center,
  Bounds,
} from "@react-three/drei";
import * as THREE from "three";

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const object = useMemo(() => scene.clone(), [scene]);
  return <primitive object={object} />;
}
function Reference() {
  return (
    <group>
      <mesh position={[0, 0.018, 0]} castShadow>
        <boxGeometry args={[0.12, 0.012, 0.6]} />
        <meshStandardMaterial
          color="#c6d2cc"
          metalness={0.3}
          roughness={0.55}
        />
      </mesh>
      <mesh position={[0.078, 0.018, 0]} castShadow>
        <boxGeometry args={[0.029, 0.007, 0.6]} />
        <meshStandardMaterial color="#4f9786" metalness={0.3} roughness={0.5} />
      </mesh>
      <mesh position={[0.17, 0.037, 0.04]} castShadow>
        <boxGeometry args={[0.08, 0.006, 0.04]} />
        <meshStandardMaterial
          color="#d8884d"
          metalness={0.6}
          roughness={0.35}
        />
      </mesh>
    </group>
  );
}
function Camera({ view }: { view: string }) {
  const { camera } = useThree();
  useEffect(() => {
    const distance = camera.position.length() || 1;
    const direction =
      view === "top"
        ? new THREE.Vector3(0, 1, 0.001)
        : view === "side"
          ? new THREE.Vector3(1, 0.08, 0)
          : new THREE.Vector3(0.8, 0.65, 1);
    camera.position.copy(direction.normalize().multiplyScalar(distance));
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, [view, camera]);
  return null;
}
function Viewer({
  url,
  view,
  wireframe,
}: {
  url?: string;
  view: string;
  wireframe: boolean;
}) {
  return (
    <div data-testid="cad-canvas" className="canvas-wrap">
      <Canvas
        camera={{ position: [0.55, 0.5, 0.7], fov: 38, near: 0.001, far: 100 }}
        gl={{ antialias: true, preserveDrawingBuffer: true }}
      >
        <color attach="background" args={["#17221f"]} />
        <ambientLight intensity={1.4} />
        <directionalLight position={[2, 4, 2]} intensity={3} />
        <directionalLight
          position={[-2, 1, -1]}
          color="#9fdbc3"
          intensity={1.2}
        />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.5}>
            <Center key={url || "reference"}>
              <group scale={url ? 0.001 : 1}>
                {url ? <Model url={url} /> : <Reference />}
              </group>
            </Center>
          </Bounds>
        </Suspense>
        <Grid
          position={[0, -0.055, 0]}
          args={[2, 2]}
          cellSize={0.025}
          sectionSize={0.1}
          cellThickness={0.45}
          sectionThickness={0.8}
          cellColor="#344b40"
          sectionColor="#536c60"
          fadeDistance={3}
          infiniteGrid
        />
        <OrbitControls
          makeDefault
          minDistance={0.05}
          maxDistance={5}
          enableDamping
        />
        <Camera view={view} />
        <Wireframe enabled={wireframe} url={url} />
      </Canvas>
    </div>
  );
}
export default memo(Viewer);
function Wireframe({ enabled, url }: { enabled: boolean; url?: string }) {
  const { scene } = useThree();
  useEffect(() => {
    const timer = setTimeout(
      () =>
        scene.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            const materials = Array.isArray(object.material)
              ? object.material
              : [object.material];
            for (const material of materials)
              if (material instanceof THREE.MeshStandardMaterial)
                material.wireframe = enabled;
          }
        }),
      200,
    );
    return () => clearTimeout(timer);
  }, [enabled, url, scene]);
  return null;
}
