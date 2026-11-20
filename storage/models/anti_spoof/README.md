# anti-spoof-mn3

`anti-spoof-mn3.onnx` is the Open Model Zoo RGB anti-spoofing model based on
MobileNetV3 and trained on CelebA-Spoof.

- Source: `https://storage.openvinotoolkit.org/repositories/open_model_zoo/public/2022.1/anti-spoof-mn3/anti-spoof-mn3.onnx`
- License: MIT for the original model; Open Model Zoo metadata is Apache-2.0.
- SHA-384: `6de4534964b723397b3e8c995cadcf43bc007cc2f9930b95ae25f76adccece5d1d4d058d0b15117b9e4a9f758424f92a`
- Input: RGB `1x3x128x128`, normalized with the model's documented mean and scale.
- Output: class `0` is real and class `1` is spoof.

The model alone does not define a safe local operating threshold. Create
`local-calibration.json` with `tools/evaluate_biometric_security.py` using real
and spoof attempts captured by the deployment camera. The calibration file is
machine-local and intentionally ignored by Git.

This model and its calibration are retained for optional offline evaluation.
They are not enforced by the current live attendance runtime, and a missing
calibration file does not block attendance.
