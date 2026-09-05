import { Suspense, useEffect, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

// Rendering discipline over polygon count (BUILD_SPEC.md Phase 6): warm key,
// cool fill, a contact shadow, slow idle orbit with easing. Models are lazy
// per species and never bundled.

function Model({ url }: { url: string }) {
  const [scene, setScene] = useState<THREE.Group | null>(null);
  useEffect(() => {
    let cancelled = false;
    new GLTFLoader().load(url, (gltf) => {
      if (cancelled) return;
      const g = gltf.scene;
      const box = new THREE.Box3().setFromObject(g);
      const size = box.getSize(new THREE.Vector3()).length() || 1;
      g.scale.setScalar(2 / size);
      const c = box.getCenter(new THREE.Vector3()).multiplyScalar(2 / size);
      g.position.sub(c);
      g.position.y += 0.6;
      g.traverse((o) => { if ((o as THREE.Mesh).isMesh) { o.castShadow = true; } });
      setScene(g);
    });
    return () => { cancelled = true; };
  }, [url]);
  return scene ? <primitive object={scene} /> : null;
}

function Orbit({ children }: { children: React.ReactNode }) {
  const ref = useRef<THREE.Group>(null);
  useFrame((_, dt) => { if (ref.current) ref.current.rotation.y += dt * 0.15; });
  return <group ref={ref}>{children}</group>;
}

export default function Model3D({ url }: { url: string }) {
  return (
    <Canvas shadows camera={{ position: [2.4, 1.4, 2.4], fov: 35 }} dpr={[1, 1.5]}>
      <color attach="background" args={["#f4f3ef"]} />
      <hemisphereLight intensity={0.5} color="#ffffff" groundColor="#c9d4e0" />
      <directionalLight position={[3, 4, 2]} intensity={1.6} color="#fff1dc" castShadow shadow-mapSize={[1024, 1024]} />
      <directionalLight position={[-3, 2, -2]} intensity={0.5} color="#cfe0ff" />
      <Suspense fallback={null}>
        <Orbit><Model url={url} /></Orbit>
      </Suspense>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.4, 0]} receiveShadow>
        <circleGeometry args={[1.6, 48]} />
        <shadowMaterial opacity={0.28} />
      </mesh>
    </Canvas>
  );
}
