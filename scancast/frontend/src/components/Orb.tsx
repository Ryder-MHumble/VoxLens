import { useEffect, useRef } from "react";
import * as THREE from "three";

/** Iridescent floating orb rendered with three.js — sits in the top-right corner. */
export function Orb({ size = 64 }: { size?: number }) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    camera.position.z = 3;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(size, size);
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const geom = new THREE.SphereGeometry(1, 96, 96);
    const uniforms = {
      uTime: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      vertexShader: /* glsl */ `
        varying vec3 vNormal;
        varying vec3 vPos;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          vPos = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        uniform float uTime;
        varying vec3 vNormal;
        varying vec3 vPos;

        vec3 hue(float t) {
          return 0.5 + 0.5 * cos(6.2831 * (vec3(0.0, 0.33, 0.67) + t));
        }

        void main() {
          vec3 viewDir = vec3(0.0, 0.0, 1.0);
          float fres = pow(1.0 - max(dot(vNormal, viewDir), 0.0), 2.2);
          float angle = atan(vPos.y, vPos.x);
          vec3 col = mix(
            hue(angle * 0.15 + uTime * 0.08 + 0.55),
            vec3(1.0),
            0.45
          );
          col = mix(col, vec3(0.85, 0.78, 1.0), fres);
          float alpha = 0.55 + fres * 0.4;
          gl_FragColor = vec4(col, alpha);
        }
      `,
    });
    const sphere = new THREE.Mesh(geom, mat);
    scene.add(sphere);

    let raf = 0;
    const start = performance.now();
    const tick = () => {
      const t = (performance.now() - start) / 1000;
      uniforms.uTime.value = t;
      sphere.rotation.y = t * 0.35;
      sphere.rotation.x = Math.sin(t * 0.4) * 0.25;
      sphere.position.y = Math.sin(t * 0.8) * 0.08;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      geom.dispose();
      mat.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [size]);

  return (
    <div
      ref={mountRef}
      style={{ width: size, height: size, filter: "drop-shadow(0 8px 24px oklch(0.7 0.2 300 / 0.35))" }}
      aria-hidden
    />
  );
}
