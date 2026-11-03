"""UniBot leaderboard snapshot (transcribed from the official JSON).

Source: https://unibot.unitree.com/leaderboard_data.json
Retrieved: 2026-11-02 (UTC), via webfetch (direct curl is blocked by the
site's EdgeOne WAF, so the payload was transcribed verbatim into this file).

Fields per model: (model_name, user_name, avg_success_rate, avg_duration_sec,
avg_step_score, [32 per-task success rates in TASKS order]).
"""

TASKS = [
    "Hang the Cup", "Fruit Basket Collection", "Pack the Doll", "Fruit Sorting",
    "Disconnect Ethernet", "Color Arrangement", "Place Photo Frames",
    "Organize Bookshelf", "Toolbox Storage", "Plug Charger", "Pick Out Battery",
    "Unlock", "Arrange Test Tubes", "Open Pill Bottle", "Organize Tools",
    "Fold Towel", "Organize Stationery", "Pack Bag", "Zip Up",
    "Paper Cup Stacking", "Clear Plates", "Spell robot", "Store Racket",
    "Conveyor Food Sorting", "Stack Cups", "Plug In Ethernet", "Stack Bowls",
    "Store Earphones", "Pack Phone", "Remove Pinned Note",
    "Organize Pencil Case", "Syringe Water Transfer",
]

MODELS = [
    ("MolmoAct2", "DexHacker", 29.7, 44.02, 39.0, [
        27.29, 27.85, 37.01, 31.76, 21.29, 37.32, 24.33, 33.02, 30.71, 30.51,
        23.46, 23.52, 28.93, 28.57, 37.20, 27.19, 30.90, 28.77, 33.42, 35.28,
        32.72, 28.62, 28.49, 32.26, 31.44, 27.54, 29.28, 27.73, 27.39, 33.75,
        24.95, 27.89]),
    ("WALL-OSS-0.5", "Generalist Robotics", 28.5, 43.74, 38.9, [
        32.89, 30.91, 25.82, 25.95, 30.09, 29.10, 26.71, 30.00, 23.96, 38.17,
        21.45, 23.18, 34.38, 30.09, 20.92, 32.15, 33.06, 27.30, 30.95, 23.65,
        27.52, 33.99, 28.02, 27.03, 34.59, 22.90, 24.59, 28.35, 21.49, 40.28,
        28.70, 23.81]),
    ("DreamZero", "World Model Lab", 27.9, 44.59, 37.9, [
        38.43, 30.77, 28.41, 35.50, 22.83, 32.78, 42.00, 25.04, 25.56, 34.50,
        22.57, 20.54, 19.53, 28.06, 23.43, 23.25, 21.51, 28.52, 21.26, 25.92,
        23.54, 22.94, 34.23, 35.38, 31.48, 16.94, 29.66, 28.52, 31.86, 30.66,
        30.30, 26.86]),
    ("Spirit-v1.5", "VLAGO", 25.9, 45.19, 34.4, [
        9.03, 24.53, 33.37, 32.24, 33.44, 25.72, 34.22, 30.05, 23.62, 19.40,
        30.03, 24.35, 30.65, 11.68, 25.35, 21.61, 26.30, 24.17, 31.36, 34.03,
        21.98, 14.37, 20.45, 34.36, 35.48, 18.75, 36.28, 32.30, 22.25, 23.17,
        21.16, 23.07]),
    ("DM0", "Embodied AI Institute", 23.5, 45.11, 31.7, [
        22.12, 32.38, 23.91, 28.78, 31.73, 25.10, 27.42, 22.96, 25.14, 18.53,
        16.17, 20.39, 23.74, 26.14, 19.15, 30.54, 9.09, 31.38, 17.09, 32.47,
        24.47, 21.17, 23.35, 17.09, 31.80, 12.87, 26.20, 25.61, 21.23, 13.31,
        26.33, 24.33]),
    ("PI-0.5", "RoboReasoner", 22.8, 43.88, 30.6, [
        15.46, 23.56, 23.26, 23.81, 23.95, 29.26, 18.10, 26.77, 22.76, 26.05,
        23.45, 28.17, 23.86, 19.79, 26.69, 16.71, 13.34, 24.59, 19.79, 33.88,
        18.05, 18.93, 24.56, 23.36, 19.87, 9.23, 11.33, 29.85, 24.72, 32.26,
        24.87, 29.35]),
    ("GigaBrain-0", "xembody", 22.6, 43.76, 29.5, [
        25.75, 27.85, 15.29, 19.83, 25.37, 26.27, 33.47, 25.33, 28.67, 20.93,
        23.88, 14.39, 17.44, 22.11, 25.46, 22.28, 25.38, 21.19, 19.65, 21.12,
        24.53, 17.03, 20.33, 37.55, 32.41, 19.30, 16.12, 23.30, 16.94, 18.86,
        12.94, 22.22]),
    ("GR00T N1.5", "Humanoid Dynamics", 20.5, 44.71, 28.1, [
        12.67, 24.50, 22.02, 18.23, 25.82, 11.38, 17.57, 19.78, 26.13, 16.47,
        25.44, 6.30, 14.67, 15.37, 29.29, 18.92, 20.16, 16.35, 13.58, 18.04,
        34.36, 17.54, 25.14, 25.96, 25.49, 14.27, 19.43, 27.40, 25.19, 26.13,
        23.39, 19.00]),
]
