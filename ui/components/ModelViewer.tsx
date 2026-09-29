"use client";
import {
  Component,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { Box3, Vector3 } from "three";
import s from "./workspace.module.css";

class Boundary extends Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className={s.placeholder}>
        Preview unavailable. STEP download remains available.
      </div>
    ) : (
      this.props.children
    );
  }
}
function Geometry({ url, ready }: { url: string; ready: () => void }) {
  const { scene } = useGLTF(url);
  const model = useMemo(() => {
    const clone = scene.clone(true);
    clone.updateMatrixWorld(true);
    const box = new Box3().setFromObject(clone);
    const size = box.getSize(new Vector3());
    const center = box.getCenter(new Vector3());
    return {
      clone,
      scale: 2 / Math.max(size.x, size.y, size.z, 1e-9),
      offset: center.multiplyScalar(-1).toArray() as [number, number, number],
    };
  }, [scene]);
  useEffect(() => ready(), [model, ready]);
  return (
    <group scale={model.scale}>
      <group position={model.offset}>
        <primitive object={model.clone} />
      </group>
    </group>
  );
}
export default function ModelViewer({
  url,
  label = "CAD model",
}: {
  url?: string;
  label?: string;
}) {
  const ref = useRef<HTMLDivElement>(null),
    [visible, setVisible] = useState(false);
  const [ready, setReady] = useState(false);
  const onReady = useCallback(() => setReady(true), []);
  useEffect(() => setReady(false), [url]);
  useEffect(() => {
    const io = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "100px" },
    );
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className={s.viewer}
      aria-label={label}
      data-geometry-ready={ready && visible}
    >
      {url && visible ? (
        <Boundary key={url}>
          <Canvas
            frameloop="demand"
            dpr={[1, 1.5]}
            camera={{ position: [3, 2, 3], fov: 36, near: 0.01, far: 100 }}
            gl={{ antialias: true, preserveDrawingBuffer: true }}
          >
            <color attach="background" args={["#e9ece3"]} />
            <ambientLight intensity={1.7} />
            <directionalLight position={[3, 5, 2]} intensity={2.5} />
            <directionalLight position={[-3, 2, -2]} intensity={1} />
            <Suspense fallback={null}>
              <Geometry url={url} ready={onReady} />
            </Suspense>
            <OrbitControls makeDefault enableDamping minPolarAngle={0.15} />
          </Canvas>
        </Boundary>
      ) : (
        <div className={s.placeholder}>
          {url ? "Model preview" : "Waiting for CAD geometry"}
        </div>
      )}
      <span className={s.viewerHint}>Drag to rotate · scroll to zoom</span>
    </div>
  );
}
