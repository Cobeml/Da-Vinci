"use client";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

export default function DroneReference({
  sensor = true,
}: {
  sensor?: boolean;
}) {
  const wing = useMemo(() => {
    const shape = new THREE.Shape();
    const points = [
      [-120, -700],
      [-30, -700],
      [80, -90],
      [80, 90],
      [-30, 700],
      [-120, 700],
      [-170, 90],
      [-170, -90],
    ];
    points.forEach(([x, z], i) =>
      i ? shape.lineTo(x, z) : shape.moveTo(x, z),
    );
    shape.closePath();
    return new THREE.ExtrudeGeometry(shape, {
      depth: 12,
      bevelEnabled: true,
      bevelSize: 2,
      bevelThickness: 2,
      bevelSegments: 2,
    });
  }, []);
  useEffect(() => () => wing.dispose(), [wing]);
  return (
    <group>
      <mesh position={[-65, 75, 0]} scale={[365, 58, 70]}>
        <sphereGeometry args={[1, 48, 24]} />
        <meshStandardMaterial color="#dce0da" roughness={0.62} />
      </mesh>
      <mesh position={[55, 119, 0]} scale={[110, 19, 47]}>
        <sphereGeometry args={[1, 32, 16]} />
        <meshStandardMaterial
          color="#536361"
          metalness={0.25}
          roughness={0.4}
        />
      </mesh>
      <mesh
        geometry={wing}
        position={[0, 99, 0]}
        rotation={[Math.PI / 2, 0, 0]}
      >
        <meshStandardMaterial color="#d4d9d1" roughness={0.6} />
      </mesh>
      {[-300, 300].map((z) => (
        <group key={z}>
          <mesh position={[-55, 98, z]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[9, 9, 650, 14]} />
            <meshStandardMaterial color="#47504b" roughness={0.55} />
          </mesh>
          {[-300, 225].map((x) => (
            <group key={x} position={[x, 112, z]}>
              <mesh>
                <cylinderGeometry args={[20, 17, 30, 24]} />
                <meshStandardMaterial
                  color="#515d55"
                  metalness={0.4}
                  roughness={0.45}
                />
              </mesh>
              <mesh position={[0, 18, 0]} rotation={[0, z < 0 ? 0.3 : -0.3, 0]}>
                <boxGeometry args={[235, 4, 15]} />
                <meshStandardMaterial color="#343f38" roughness={0.55} />
              </mesh>
              <mesh position={[0, 23, 0]}>
                <sphereGeometry args={[12, 16, 8]} />
                <meshStandardMaterial color="#a3aca3" />
              </mesh>
            </group>
          ))}
        </group>
      ))}
      <mesh position={[-360, 95, 0]}>
        <boxGeometry args={[95, 9, 520]} />
        <meshStandardMaterial color="#d4d9d1" />
      </mesh>
      {[-205, 205].map((z) => (
        <mesh key={z} position={[-370, 145, z]} rotation={[0, 0, -0.22]}>
          <boxGeometry args={[75, 100, 8]} />
          <meshStandardMaterial color="#bac5b8" />
        </mesh>
      ))}
      {sensor && (
        <group>
          <mesh position={[190, 30, 0]}>
            <boxGeometry args={[108, 8, 78]} />
            <meshStandardMaterial color="#747f74" />
          </mesh>
          <mesh position={[190, -9, 0]} scale={[16, 16, 23]}>
            <sphereGeometry args={[1, 24, 16]} />
            <meshStandardMaterial color="#535e58" />
          </mesh>
          <mesh position={[208, -9, 0]} rotation={[0, 0, -Math.PI / 2]}>
            <cylinderGeometry args={[10, 12, 12, 24]} />
            <meshStandardMaterial
              color="#182b2c"
              metalness={0.5}
              roughness={0.22}
            />
          </mesh>
        </group>
      )}
    </group>
  );
}
