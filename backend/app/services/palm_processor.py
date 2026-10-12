"""Robust and tolerant Palm detection, ROI extraction, and biometric feature extraction."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
import cv2
import numpy as np


class PalmFeatureExtractor(ABC):
    """Abstract base class for palm biometric feature extractors."""

    @abstractmethod
    def extract(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extracts a normalized 1D biometric feature vector from an input BGR image."""
        pass


class OpenCVPalmFeatureExtractor(PalmFeatureExtractor):
    """Ultra-tolerant palm feature extractor that accommodates realistic positioning,

    distance variations (5cm–20cm), hand rotation, and off-center alignment.
    """

    def __init__(self, roi_size: int = 128):
        self.roi_size = roi_size
        self.clahe = cv2.createCLAHE(clipLimit=3.5, tileGridSize=(8, 8))
        self.gabor_kernels = self._build_gabor_bank()

    def _build_gabor_bank(self) -> list:
        """Builds a multi-scale, multi-orientation bank of Gabor filters."""
        kernels = []
        ksize = 17
        gamma = 0.5
        psi = 0.0

        for lambd in [6.0, 10.0]:
            sigma = lambd * 0.56
            for theta in [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]:
                kern = cv2.getGaborKernel(
                    (ksize, ksize), sigma, theta, lambd, gamma, psi, ktype=cv2.CV_32F
                )
                kern -= kern.mean()
                norm = np.linalg.norm(kern)
                if norm > 0:
                    kern /= norm
                kernels.append(kern)
        return kernels

    def segment_palm(self, image: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Segments hand/palm with dual color-space + adaptive Otsu fallback."""
        h, w = image.shape[:2]
        blurred = cv2.GaussianBlur(image, (5, 5), 0)

        # 1. Skin tone thresholding in YCrCb & HSV
        ycrcb = cv2.cvtColor(blurred, cv2.COLOR_BGR2YCrCb)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

        ycrcb_mask = cv2.inRange(
            ycrcb,
            np.array([0, 128, 70], dtype=np.uint8),
            np.array([255, 180, 135], dtype=np.uint8)
        )
        hsv_mask = cv2.inRange(
            hsv,
            np.array([0, 15, 35], dtype=np.uint8),
            np.array([30, 255, 255], dtype=np.uint8)
        )

        skin_mask = cv2.bitwise_or(ycrcb_mask, hsv_mask)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find largest contour
        contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 2. Fallback to adaptive/Otsu thresholding if hand color varies under bright LED
        if not contours or max(cv2.contourArea(c) for c in contours) < (0.05 * w * h):
            gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
            _, otsu_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            otsu_mask = cv2.morphologyEx(otsu_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours, _ = cv2.findContours(otsu_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # If still no contour, use central crop as reliable fallback
        if not contours:
            center_crop = image[h // 6 : 5 * h // 6, w // 6 : 5 * w // 6]
            return center_crop, None

        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)

        if area < (0.04 * w * h):
            center_crop = image[h // 6 : 5 * h // 6, w // 6 : 5 * w // 6]
            return center_crop, None

        # 3. Locate ROI center (Distance transform or Bounding Box)
        x, y, bw, bh = cv2.boundingRect(largest_contour)
        cx, cy = x + bw // 2, y + bh // 2
        half_side = max(min(bw, bh) // 2, 25)

        x1 = max(0, cx - half_side)
        y1 = max(0, cy - half_side)
        x2 = min(w, cx + half_side)
        y2 = min(h, cy + half_side)

        roi = image[y1:y2, x1:x2]
        if roi.size == 0 or roi.shape[0] < 10 or roi.shape[1] < 10:
            roi = image[h // 6 : 5 * h // 6, w // 6 : 5 * w // 6]

        return roi, largest_contour

    def extract(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Extracts normalized biometric feature vector from the segmented region."""
        roi, _ = self.segment_palm(image)
        if roi is None or roi.size == 0:
            return None

        # 1. Normalize ROI to standard size
        roi_resized = cv2.resize(roi, (self.roi_size, self.roi_size), interpolation=cv2.INTER_AREA)

        # 2. Convert to Grayscale & apply CLAHE illumination equalization
        gray_roi = cv2.cvtColor(roi_resized, cv2.COLOR_BGR2GRAY)
        equalized_roi = self.clahe.apply(gray_roi)

        # 3. Multi-Scale Gabor Bank Responses
        feature_parts = []
        grid_size = 16
        num_blocks = self.roi_size // grid_size

        float_roi = equalized_roi.astype(np.float32)

        for kern in self.gabor_kernels:
            filtered = cv2.filter2D(float_roi, cv2.CV_32F, kern)
            filtered_mag = np.abs(filtered)

            for by in range(num_blocks):
                for bx in range(num_blocks):
                    block = filtered_mag[
                        by * grid_size : (by + 1) * grid_size,
                        bx * grid_size : (bx + 1) * grid_size,
                    ]
                    feature_parts.append(float(np.mean(block)))
                    feature_parts.append(float(np.std(block)))

        # 4. Sobel Gradient Features
        sobel_x = cv2.Sobel(equalized_roi, cv2.CV_32F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(equalized_roi, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.sqrt(sobel_x ** 2 + sobel_y ** 2)

        for by in range(num_blocks):
            for bx in range(num_blocks):
                g_block = grad_mag[
                    by * grid_size : (by + 1) * grid_size,
                    bx * grid_size : (bx + 1) * grid_size,
                ]
                feature_parts.append(float(np.mean(g_block)))
                feature_parts.append(float(np.std(g_block)))

        feature_vector = np.array(feature_parts, dtype=np.float32)

        # 5. L2-Normalize
        norm = np.linalg.norm(feature_vector)
        if norm > 1e-6:
            feature_vector = feature_vector / norm
        else:
            return None

        return feature_vector


palm_extractor = OpenCVPalmFeatureExtractor()
