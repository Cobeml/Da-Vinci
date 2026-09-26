'use client';
import { Suspense, useEffect, useRef } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { Grid, OrbitControls, useGLTF, Center, Bounds, Html } from '@react-three/drei';
import * as THREE from 'three';

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene.clone()} />;
}
function Reference() {
  return <group>
    <mesh position={[0, .018, 0]} castShadow><boxGeometry args={[.12, .012, .6]} /><meshStandardMaterial color="#c6d2cc" metalness={.3} roughness={.55} /></mesh>
    <mesh position={[.078, .018, 0]} castShadow><boxGeometry args={[.029, .007, .6]} /><meshStandardMaterial color="#4f9786" metalness={.3} roughness={.5} /></mesh>
    <mesh position={[.17, .037, .04]} castShadow><boxGeometry args={[.08, .006, .04]} /><meshStandardMaterial color="#d8884d" metalness={.6} roughness={.35} /></mesh>
  </group>;
}
function Camera({view}:{view:string}) {
  const {camera} = useThree();
  useEffect(() => {
    const distance = camera.position.length() || 1;
    const direction = view === 'top' ? new THREE.Vector3(0,1,.001) : view === 'side' ? new THREE.Vector3(1,.08,0) : new THREE.Vector3(.8,.65,1);
    camera.position.copy(direction.normalize().multiplyScalar(distance));
    camera.lookAt(0,0,0); camera.updateProjectionMatrix();
  }, [view,camera]);
  return null;
}
export default function Viewer({url,view,wireframe}:{url?:string;view:string;wireframe:boolean}) {
  return <div data-testid="cad-canvas" className="canvas-wrap">
    <Canvas camera={{position:[.55,.5,.7],fov:38,near:.001,far:100}} gl={{antialias:true,preserveDrawingBuffer:true}}>
      <color attach="background" args={['#17221f']} />
      <ambientLight intensity={1.4} />
      <directionalLight position={[2,4,2]} intensity={3} />
      <directionalLight position={[-2,1,-1]} color="#9fdbc3" intensity={1.2} />
      <Suspense fallback={<Html center><span className="loading-model">Loading geometry…</span></Html>}>
        <Bounds fit clip observe margin={1.5}>
          <Center key={url || 'reference'}>
            <group rotation={url ? [-Math.PI/2,0,0] : [0,0,0]}>
              {url ? <Model url={url} /> : <Reference />}
            </group>
          </Center>
        </Bounds>
      </Suspense>
      <Grid position={[0,-.055,0]} args={[2,2]} cellSize={.025} sectionSize={.1} cellThickness={.45} sectionThickness={.8} cellColor="#344b40" sectionColor="#536c60" fadeDistance={3} infiniteGrid />
      <OrbitControls makeDefault minDistance={.05} maxDistance={5} enableDamping />
      <Camera view={view} />
      <Wireframe enabled={wireframe} url={url} />
    </Canvas>
  </div>;
}
function Wireframe({enabled,url}:{enabled:boolean;url?:string}) {
  const {scene} = useThree();
  useEffect(() => {
    const timer = setTimeout(() => scene.traverse(object => {
      if (object instanceof THREE.Mesh) {
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        for (const material of materials) if (material instanceof THREE.MeshStandardMaterial) material.wireframe = enabled;
      }
    }),200);
    return () => clearTimeout(timer);
  },[enabled,url,scene]);
  return null;
}
