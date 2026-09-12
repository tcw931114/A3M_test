import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
import { OrbitControls } from 'https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'https://unpkg.com/three@0.160.0/examples/jsm/loaders/GLTFLoader.js';

const viewer = document.querySelector('#viewer');
const viewerFrame = document.querySelector('#viewer-frame');
const loadingState = document.querySelector('#loading-state');
const loadingLabel = document.querySelector('#loading-label');
const sceneStatus = document.querySelector('#scene-status');

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xd6dfd8);

const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
camera.position.set(18, 14, 18);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewer.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.screenSpacePanning = true;
controls.minDistance = 0.5;
controls.maxDistance = 2500;

scene.add(new THREE.HemisphereLight(0xf4f6ed, 0x657568, 2.4));
const sun = new THREE.DirectionalLight(0xfff7df, 3.2);
sun.position.set(40, 70, 25);
sun.castShadow = true;
scene.add(sun);

const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(5000, 5000),
    new THREE.MeshStandardMaterial({ color: 0xc7d2c9, roughness: 1 })
);
ground.rotation.x = -Math.PI / 2;
ground.position.y = -0.03;
ground.receiveShadow = true;
scene.add(ground);

let initialCamera;

function resize() {
    const { clientWidth, clientHeight } = viewer;
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(clientWidth, clientHeight, false);
}

function frameModel(model) {
    const bounds = new THREE.Box3().setFromObject(model);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z);
    const distance = maxDimension * 1.35;

    model.position.sub(center);
    model.position.y += size.y / 2;
    controls.target.set(0, size.y * 0.35, 0);
    camera.position.set(distance * 0.9, distance * 0.65, distance * 0.9);
    camera.near = Math.max(maxDimension / 1000, 0.01);
    camera.far = Math.max(maxDimension * 100, 1000);
    camera.updateProjectionMatrix();
    controls.update();
    initialCamera = { position: camera.position.clone(), target: controls.target.clone() };
}

function loadGlb() {
    return new Promise((resolve, reject) => new GLTFLoader().load(
        './model.glb',
        (gltf) => {
            const model = gltf.scene;
            model.traverse((object) => {
                if (object.isMesh) {
                    object.castShadow = true;
                    object.receiveShadow = true;
                }
            });
            scene.add(model);
            frameModel(model);
            resolve();
        },
        (progress) => {
            if (progress.total) {
                loadingLabel.textContent = `Loading model ${Math.round(progress.loaded / progress.total * 100)}%`;
            }
        },
        reject
    ));
}

loadGlb()
    .then(() => {
        sceneStatus.textContent = 'Scene ready';
        loadingState.classList.add('is-hidden');
    })
    .catch((error) => {
        console.error(error);
        loadingLabel.textContent = 'Unable to load map data';
        sceneStatus.textContent = 'Asset unavailable';
        document.querySelector('.status-dot').style.background = '#b64d43';
    });

document.querySelector('#reset-view').addEventListener('click', () => {
    if (!initialCamera) return;
    camera.position.copy(initialCamera.position);
    controls.target.copy(initialCamera.target);
    controls.update();
});

document.querySelector('#fullscreen').addEventListener('click', () => {
    if (!document.fullscreenElement) viewerFrame.requestFullscreen();
    else document.exitFullscreen();
});

window.addEventListener('resize', resize);
resize();

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();
