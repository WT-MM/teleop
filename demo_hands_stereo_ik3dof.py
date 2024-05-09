import asyncio
from copy import deepcopy
import os
import time
import math
from typing import List, Dict

import cv2
import numpy as np
from numpy.typing import NDArray
import pybullet as p
import pybullet_data
from vuer import Vuer, VuerSession
from vuer.schemas import  Hands, ImageBackground, PointLight, Urdf

# web urdf is used for vuer
URDF_WEB: str = (
    "https://raw.githubusercontent.com/kscalelabs/webstompy/master/urdf/stompy_tiny_glb/robot.urdf"
)
# local urdf is used for pybullet
URDF_LOCAL: str = f"{os.path.dirname(__file__)}/urdf/stompy_tiny/robot.urdf"

# starting positions for robot trunk relative to world frames
START_POS_TRUNK_VUER: NDArray = np.array([0, 1, 0])
START_EUL_TRUNK_VUER: NDArray = np.array([-math.pi / 2, 0, 0])
START_POS_TRUNK_PYBULLET: NDArray = np.array([0, 0, 1])
START_EUL_TRUNK_PYBULLET: NDArray = np.array([-math.pi / 4, 0, 0])

# starting positions for robot end effectors are defined relative to robot trunk frame
# which is right in the middle of the chest
START_POS_EER_VUER: NDArray = np.array([-0.2, -0.2, -0.2])
START_POS_EEL_VUER: NDArray = np.array([0.2, -0.2, -0.2])
START_POS_EER_VUER += START_POS_TRUNK_VUER
START_POS_EEL_VUER += START_POS_TRUNK_VUER

# conversion between PyBullet and Vuer axes
PB_TO_VUER_AXES: NDArray = np.array([0, 2, 1], dtype=np.uint8)
PB_TO_VUER_AXES_SIGN: NDArray = np.array([-1, 1, 1], dtype=np.int8)

# starting joint positions (Q means "joint angles")
START_Q: Dict[str, float] = {
    # head (2dof)
    "joint_head_1_x4_1_dof_x4": -1.0,
    "joint_head_1_x4_2_dof_x4": 0.0,
    # right leg (10dof)
    "joint_legs_1_x8_1_dof_x8": -0.50,
    "joint_legs_1_right_leg_1_x8_1_dof_x8": -0.50,
    "joint_legs_1_right_leg_1_x10_2_dof_x10": -0.97,
    "joint_legs_1_right_leg_1_knee_revolute": 0.10,
    "joint_legs_1_right_leg_1_ankle_revolute": 0.0,
    "joint_legs_1_right_leg_1_x4_1_dof_x4": 0.0,
    # left leg (6dof)
    "joint_legs_1_x8_2_dof_x8": 0.50,
    "joint_legs_1_left_leg_1_x8_1_dof_x8": -0.50,
    "joint_legs_1_left_leg_1_x10_1_dof_x10": 0.97,
    "joint_legs_1_left_leg_1_knee_revolute": -0.10,
    "joint_legs_1_left_leg_1_ankle_revolute": 0.0,
    "joint_legs_1_left_leg_1_x4_1_dof_x4": 0.0,
    # right arm (6dof)
    "joint_right_arm_1_x8_1_dof_x8": 1.7,
    "joint_right_arm_1_x8_2_dof_x8": 1.6,
    "joint_right_arm_1_x6_1_dof_x6": 0.34,
    "joint_right_arm_1_x6_2_dof_x6": 1.6,
    "joint_right_arm_1_x4_1_dof_x4": 1.4,
    "joint_right_arm_1_hand_1_x4_1_dof_x4": -0.26,
    # left arm (6dof)
    "joint_left_arm_2_x8_1_dof_x8": -1.7,
    "joint_left_arm_2_x8_2_dof_x8": -1.6,
    "joint_left_arm_2_x6_1_dof_x6": -0.34,
    "joint_left_arm_2_x6_2_dof_x6": -1.6,
    "joint_left_arm_2_x4_1_dof_x4": -1.4,
    "joint_left_arm_2_hand_1_x4_1_dof_x4": -1.7,
    # right hand (2dof)
    "joint_right_arm_1_hand_1_slider_1": 0.0,
    "joint_right_arm_1_hand_1_slider_2": 0.0,
    # left hand (2dof)
    "joint_left_arm_2_hand_1_slider_1": 0.0,
    "joint_left_arm_2_hand_1_slider_2": 0.0,
}

# link names are based on the URDF
# EER means "end effector right"
# EEL means "end effector left"
EER_LINK: str = "link_right_arm_1_hand_1_x4_2_outer_1"
EEL_LINK: str = "link_left_arm_2_hand_1_x4_2_outer_1"

# kinematic chains for each arm and hand
EER_CHAIN_ARM: List[str] = [
    "joint_right_arm_1_x8_1_dof_x8",
    "joint_right_arm_1_x8_2_dof_x8",
    "joint_right_arm_1_x6_1_dof_x6",
    "joint_right_arm_1_x6_2_dof_x6",
    "joint_right_arm_1_x4_1_dof_x4",
    "joint_right_arm_1_hand_1_x4_1_dof_x4",
]
EEL_CHAIN_ARM: List[str] = [
    "joint_left_arm_2_x8_1_dof_x8",
    "joint_left_arm_2_x8_2_dof_x8",
    "joint_left_arm_2_x6_1_dof_x6",
    "joint_left_arm_2_x6_2_dof_x6",
    "joint_left_arm_2_x4_1_dof_x4",
    "joint_left_arm_2_hand_1_x4_1_dof_x4",
]
EER_CHAIN_HAND: List[str] = [
    "joint_right_arm_1_hand_1_slider_1",
    "joint_right_arm_1_hand_1_slider_2",
]
EEL_CHAIN_HAND: List[str] = [
    "joint_left_arm_2_hand_1_slider_1",
    "joint_left_arm_2_hand_1_slider_2",
]

# PyBullet IK will output a 37dof list in this exact order
IK_Q_LIST: List[str] = [
    "joint_head_1_x4_1_dof_x4",
    "joint_head_1_x4_2_dof_x4",
    "joint_right_arm_1_x8_1_dof_x8",
    "joint_right_arm_1_x8_2_dof_x8",
    "joint_right_arm_1_x6_1_dof_x6",
    "joint_right_arm_1_x6_2_dof_x6",
    "joint_right_arm_1_x4_1_dof_x4",
    "joint_right_arm_1_hand_1_x4_1_dof_x4",
    "joint_right_arm_1_hand_1_slider_1",
    "joint_right_arm_1_hand_1_slider_2",
    "joint_right_arm_1_hand_1_x4_2_dof_x4",
    "joint_left_arm_2_x8_1_dof_x8",
    "joint_left_arm_2_x8_2_dof_x8",
    "joint_left_arm_2_x6_1_dof_x6",
    "joint_left_arm_2_x6_2_dof_x6",
    "joint_left_arm_2_x4_1_dof_x4",
    "joint_left_arm_2_hand_1_x4_1_dof_x4",
    "joint_left_arm_2_hand_1_slider_1",
    "joint_left_arm_2_hand_1_slider_2",
    "joint_left_arm_2_hand_1_x4_2_dof_x4",
    "joint_torso_1_x8_1_dof_x8",
    "joint_legs_1_x8_1_dof_x8",
    "joint_legs_1_right_leg_1_x8_1_dof_x8",
    "joint_legs_1_right_leg_1_x10_2_dof_x10",
    "joint_legs_1_right_leg_1_knee_revolute",
    "joint_legs_1_right_leg_1_x10_1_dof_x10",
    "joint_legs_1_right_leg_1_ankle_revolute",
    "joint_legs_1_right_leg_1_x6_1_dof_x6",
    "joint_legs_1_right_leg_1_x4_1_dof_x4",
    "joint_legs_1_x8_2_dof_x8",
    "joint_legs_1_left_leg_1_x8_1_dof_x8",
    "joint_legs_1_left_leg_1_x10_1_dof_x10",
    "joint_legs_1_left_leg_1_knee_revolute",
    "joint_legs_1_left_leg_1_x10_2_dof_x10",
    "joint_legs_1_left_leg_1_ankle_revolute",
    "joint_legs_1_left_leg_1_x6_1_dof_x6",
    "joint_legs_1_left_leg_1_x4_1_dof_x4",
]

# camera streaming is done throgh OpenCV
IMAGE_WIDTH: int = 1280
IMAGE_HEIGHT: int = 480
aspect_ratio: float = IMAGE_WIDTH / IMAGE_HEIGHT
CAMERA_FPS: int = 60
VUER_IMG_QUALITY: int = 20
BGR_TO_RGB: NDArray = np.array([2, 1, 0], dtype=np.uint8)
CAMERA_DISTANCE: int = 5
IMAGE_POS: NDArray = np.array([0, 0, -10])
IMAGE_EUL: NDArray = np.array([0, 0, 0])

print("Starting camera")
img_lock = asyncio.Lock()
img: NDArray[np.uint8] = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH, 3), dtype=np.uint8)
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH, IMAGE_WIDTH)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, IMAGE_HEIGHT)
cam.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
print("\t ... done")


async def update_image() -> None:
    global cam
    if not cam.isOpened():
        raise ValueError("Camera is not available")
    # start = time.time()
    ret, frame = cam.read()
    if ret:
        async with img_lock:
            global img
            img = frame[:, :, BGR_TO_RGB]
    else:
        print("Failed to read frame")
    # print(f"Time to update image: {time.time() - start}")


# PyBullet inverse kinematics (IK) params
# damping determines which joints are used for ik
# TODO: more custom damping will allow for legs/torso to help reach ee target
DAMPING_CHAIN: float = 0.1
DAMPING_NON_CHAIN: float = 10.0

# PyBullet init
HEADLESS: bool = True
if HEADLESS:
    print("Starting PyBullet in headless mode.")
    clid = p.connect(p.DIRECT)
else:
    print("Starting PyBullet in GUI mode.")
    clid = p.connect(p.SHARED_MEMORY)
    if clid < 0:
        p.connect(p.GUI)
p.setAdditionalSearchPath(pybullet_data.getDataPath())
pb_robot_id = p.loadURDF(URDF_LOCAL, [0, 0, 0], useFixedBase=True)
p.setGravity(0, 0, 0)
p.resetBasePositionAndOrientation(
    pb_robot_id,
    START_POS_TRUNK_PYBULLET,
    p.getQuaternionFromEuler(START_EUL_TRUNK_PYBULLET),
)
pb_num_joints: int = p.getNumJoints(pb_robot_id)
print(f"\t number of joints: {pb_num_joints}")
pb_joint_names: List[str] = [""] * pb_num_joints
pb_child_link_names: List[str] = [""] * pb_num_joints
pb_joint_upper_limit: List[float] = [0.0] * pb_num_joints
pb_joint_lower_limit: List[float] = [0.0] * pb_num_joints
pb_joint_ranges: List[float] = [0.0] * pb_num_joints
pb_start_q: List[float] = [0.0] * pb_num_joints
pb_damping: List[float] = [0.0] * pb_num_joints
pb_q_map: Dict[str, int] = {}
for i in range(pb_num_joints):
    info = p.getJointInfo(pb_robot_id, i)
    name = info[1].decode("utf-8")
    pb_joint_names[i] = name
    pb_child_link_names[i] = info[12].decode("utf-8")
    pb_joint_lower_limit[i] = info[9]
    pb_joint_upper_limit[i] = info[10]
    pb_joint_ranges[i] = abs(info[10] - info[9])
    if name in START_Q:
        pb_start_q[i] = START_Q[name]
    if name in EER_CHAIN_ARM or name in EEL_CHAIN_ARM:
        pb_damping[i] = DAMPING_CHAIN
    else:
        pb_damping[i] = DAMPING_NON_CHAIN
    if name in IK_Q_LIST:
        pb_q_map[name] = i
pb_eer_id = pb_child_link_names.index(EER_LINK)
pb_eel_id = pb_child_link_names.index(EEL_LINK)
for i in range(pb_num_joints):
    p.resetJointState(pb_robot_id, i, pb_start_q[i])
print("\t ... done")

# Vuer rendering params
MAX_FPS: int = 60
VUER_LIGHT_POS: NDArray = np.array([0, 2, 2])
VUER_LIGHT_INTENSITY: float = 10.0

# Vuer hand tracking and pinch detection params
HAND_FPS: int = 30
INDEX_FINGER_TIP_ID: int = 9
THUMB_FINGER_TIP_ID: int = 4
MIDLE_FINGER_TIP_ID: int = 14
PINCH_DIST_OPENED: float = 0.10  # 10cm
PINCH_DIST_CLOSED: float = 0.01  # 1cm

# pre-compute gripper "slider" ranges for faster callback
EE_S_MIN: float = -0.034
EE_S_MAX: float = 0.0
ee_s_range: float = EE_S_MAX - EE_S_MIN

# global variables get updated by various async functions
q_lock = asyncio.Lock()
q: Dict[str, float] = deepcopy(START_Q)
goal_pos_eer: NDArray = START_POS_EER_VUER
goal_orn_eer: NDArray = p.getQuaternionFromEuler(START_EUL_TRUNK_VUER)
goal_pos_eel: NDArray = START_POS_EEL_VUER
goal_orn_eel: NDArray = p.getQuaternionFromEuler(START_EUL_TRUNK_VUER)


async def ik(arm: str) -> None:
    # start_time = time.time()
    if arm == "right":
        global goal_pos_eer, goal_orn_eer
        ee_id = pb_eer_id
        ee_chain = EER_CHAIN_ARM
        pos = goal_pos_eer
        orn = goal_orn_eer
    else:
        global goal_pos_eel, goal_orn_eel
        ee_id = pb_eel_id
        ee_chain = EEL_CHAIN_ARM
        pos = goal_pos_eel
        orn = goal_orn_eel
    # print(f"ik {arm} {pos} {orn}")
    pb_q = p.calculateInverseKinematics(
        pb_robot_id,
        ee_id,
        pos,
        orn,
        pb_joint_lower_limit,
        pb_joint_upper_limit,
        pb_joint_ranges,
        pb_start_q,
    )
    async with q_lock:
        global q
        for i, val in enumerate(pb_q):
            joint_name = IK_Q_LIST[i]
            if joint_name in ee_chain:
                q[joint_name] = val
                p.resetJointState(pb_robot_id, pb_q_map[joint_name], val)
    # print(f"ik {arm} took {time.time() - start_time} seconds")


app = Vuer()


@app.add_handler("HAND_MOVE")
async def hand_handler(event, _):
    # right hand
    rindex_pos: NDArray = np.array(event.value["rightLandmarks"][INDEX_FINGER_TIP_ID])
    rthumb_pos: NDArray = np.array(event.value["rightLandmarks"][THUMB_FINGER_TIP_ID])
    rpinch_dist: NDArray = np.linalg.norm(rindex_pos - rthumb_pos)
    # index finger to thumb pinch turns on tracking
    if rpinch_dist < PINCH_DIST_CLOSED:
        # print("Pinch detected in right hand")
        # NOTE: right hand controls left arm and left gripper
        global goal_pos_eel
        goal_pos_eel = np.multiply(rthumb_pos[PB_TO_VUER_AXES], PB_TO_VUER_AXES_SIGN)
        # print(f"goal_pos_eer {goal_pos_eer}")
        # pinching with middle finger controls gripper
        rmiddl_pos: NDArray = np.array(event.value["rightLandmarks"][MIDLE_FINGER_TIP_ID])
        rgrip_dist: float = np.linalg.norm(rthumb_pos - rmiddl_pos) / PINCH_DIST_OPENED
        # print(f"right gripper at {rgrip_dist}")
        _s: float = EE_S_MIN + rgrip_dist * ee_s_range
        async with q_lock:
            q["joint_left_arm_2_hand_1_slider_1"] = _s
            q["joint_left_arm_2_hand_1_slider_2"] = _s
    # left hand
    lindex_pos: NDArray = np.array(event.value["leftLandmarks"][INDEX_FINGER_TIP_ID])
    lthumb_pos: NDArray = np.array(event.value["leftLandmarks"][THUMB_FINGER_TIP_ID])
    lpinch_dist: NDArray = np.linalg.norm(lindex_pos - lthumb_pos)
    # index finger to thumb pinch turns on tracking
    if lpinch_dist < PINCH_DIST_CLOSED:
        # print("Pinch detected in left hand")
        # NOTE: left hand controls right arm and right gripper
        global goal_pos_eer
        goal_pos_eer = np.multiply(lthumb_pos[PB_TO_VUER_AXES], PB_TO_VUER_AXES_SIGN)
        # print(f"goal_pos_eel {goal_pos_eel}")
        # pinching with middle finger controls gripper
        lmiddl_pos: NDArray = np.array(event.value["leftLandmarks"][MIDLE_FINGER_TIP_ID])
        lgrip_dist: float = np.linalg.norm(lthumb_pos - lmiddl_pos) / PINCH_DIST_OPENED
        _s: float = EE_S_MIN + lgrip_dist * ee_s_range
        # print(f"left gripper at {lgrip_dist}")
        async with q_lock:
            q["joint_right_arm_1_hand_1_slider_1"] = _s
            q["joint_right_arm_1_hand_1_slider_2"] = _s


@app.spawn(start=True)
async def main(session: VuerSession):
    session.upsert @ PointLight(intensity=VUER_LIGHT_INTENSITY, position=VUER_LIGHT_POS)
    session.upsert @ Hands(fps=HAND_FPS, stream=True, key="hands")
    await asyncio.sleep(0.1)
    session.upsert @ Urdf(
        src=URDF_WEB,
        jointValues=START_Q,
        position=START_POS_TRUNK_VUER,
        rotation=START_EUL_TRUNK_VUER,
        key="robot",
    )
    global q, img
    while True:
        await asyncio.gather(
            ik("left"),  # ~1ms
            ik("right"),  # ~1ms
            update_image(),  # ~10ms
            asyncio.sleep(1 / MAX_FPS),  # ~16ms @ 60fps
        )
        async with q_lock:
            session.upsert @ Urdf(
                src=URDF_WEB,
                jointValues=q,
                position=START_POS_TRUNK_VUER,
                rotation=START_EUL_TRUNK_VUER,
                key="robot",
            )
        async with img_lock:
            session.upsert(
                ImageBackground(
                    img,
                    # TODO: test ['b64png', 'b64jpeg']
                    format="jpg",
                    quality=VUER_IMG_QUALITY,
                    interpolate=True,
                    fixed=True,
                    aspect=aspect_ratio,
                    distanceToCamera=CAMERA_DISTANCE,
                    position=IMAGE_POS,
                    rotation=IMAGE_EUL,
                    key="video",
                ),
                to="bgChildren",
            )
