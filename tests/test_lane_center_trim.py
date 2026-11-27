# Unit tests for LaneCenterTrim (angle-mode lane centering / advanced lane positioning).
#
# Isolated from CarController/LateralAngleExt -- exercises the class directly against a
# minimal fake modelV2-shaped object.

import unittest
from types import SimpleNamespace

import numpy as np

from ...car.ford.interface import CarInterface
from ...car.ford.values import CAR
from ..core.carcontroller_ext import InputTracker, SharedLateralState
from ..core.lane_center_trim import LaneCenterTrim, _CORRECTION_ROC_PER_TICK
from ..core.lateral_angle_ext import LateralAngleExt
from ..params.param_store import ParamStore


class _XY:
  def __init__(self, x, y):
    self.x = x
    self.y = y


class _Position:
  def __init__(self, x, y):
    self.x = x
    self.y = y


class _Model:
  def __init__(self, lane_lines, probs, stds, pos_x, pos_y):
    self.laneLines = lane_lines
    self.laneLineProbs = probs
    self.laneLineStds = stds # add stds
    self.position = _Position(pos_x, pos_y)


def _good_model(lane_center_y=0.0, model_y=0.0, width=3.7, probs=(0.9, 0.9, 0.9, 0.9), stds=(0.1, 0.1, 0.1, 0.1)):
  """Confident lane lines (probability + typical width) centered at lane_center_y."""
  xs = list(range(0, 60, 2))
  half = width / 2.0
  lane_lines = [
    _XY(xs, [lane_center_y - half - 3.7] * len(xs)),  # far left (unused)
    _XY(xs, [lane_center_y - half] * len(xs)),         # ego left
    _XY(xs, [lane_center_y + half] * len(xs)),         # ego right
    _XY(xs, [lane_center_y + half + 3.7] * len(xs)),  # far right (unused)
  ]
  pos_x = list(range(0, 60, 2))
  pos_y = [model_y] * len(pos_x)
  return _Model(lane_lines, list(probs), list(stds), pos_x, pos_y)


def _no_lanelines_model(model_y=0.0):
  """No lane lines detected at all (e.g. center-stripe-only road) -- zero probability on both
  ego lines. laneLines arrays still present/well-formed (as modelV2 always publishes them),
  just untrustworthy."""
  return _good_model(model_y=model_y, probs=(0.0, 0.0, 0.0, 0.0))


def _one_sided_model(model_y=0.0):
  """Only the right lane line is confidently detected (e.g. curb on the left, no line there) --
  the real-world case this blend exists for."""
  return _good_model(model_y=model_y, probs=(0.9, 0.05, 0.9, 0.9))


class TestLaneCenterTrim(unittest.TestCase):
  V_EGO = 15.0  # m/s -- at/above the 9-15 m/s ramp top, full speed authority

  def setUp(self):
    self.trim = LaneCenterTrim()

  def _run(self, model, kappa_cmd=0.0, enabled=True, offset=0.0, gain=1.0, lat_active=True,
            lane_change=False, v_ego=None, iterations=1, lane_full=None):
    # lane_full=None leaves the argument out, as every caller before the setting did
    extra = () if lane_full is None else (lane_full,)
    result = kappa_cmd
    for _ in range(iterations):
      result = self.trim.update(kappa_cmd, model, v_ego if v_ego is not None else self.V_EGO,
                                 enabled, offset, gain, lat_active, lane_change, *extra)
    return result

  def test_disabled_no_correction(self):
    model = _good_model()
    self._run(model, enabled=False, offset=1.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  def test_inactive_no_correction(self):
    model = _good_model()
    self._run(model, lat_active=False, offset=1.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  def test_lane_change_no_correction(self):
    model = _good_model()
    self._run(model, lane_change=True, offset=1.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  def test_no_model_no_correction(self):
    self._run(None, offset=1.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  def test_zero_offset_centered_no_correction(self):
    # Model already tracks lane center exactly; no error to correct.
    model = _good_model(lane_center_y=0.0, model_y=0.0)
    self._run(model, offset=0.0, iterations=50)
    self.assertAlmostEqual(self.trim.correction, 0.0, places=6)

  def test_offset_converges_to_clipped_ceiling(self):
    # A large offset saturates the raw correction against its safety ceiling; full gain and full
    # speed authority means the filtered correction converges to that ceiling.
    model = _good_model()
    self._run(model, offset=5.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=4)

  def test_gain_scales_correction_linearly(self):
    model = _good_model()
    self._run(model, offset=5.0, gain=0.25, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.001, places=4)

  def test_negative_offset_flips_sign(self):
    model = _good_model()
    self._run(model, offset=-5.0, gain=0.5, iterations=500)
    self.assertAlmostEqual(self.trim.correction, -0.002, places=4)

  def test_speed_ramp_zero_below_9ms(self):
    model = _good_model()
    self._run(model, offset=5.0, gain=1.0, v_ego=5.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  def test_speed_ramp_partial_between_9_and_15ms(self):
    model = _good_model()
    self._run(model, offset=5.0, gain=0.5, v_ego=12.0, iterations=500)
    # speed_factor at 12 m/s is 0.5 on the [9, 15] -> [0, 1] ramp
    self.assertAlmostEqual(self.trim.correction, 0.001, places=4)

  def test_added_to_kappa_cmd(self):
    model = _good_model()
    result = self._run(model, kappa_cmd=0.01, offset=5.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(result, 0.01 + 0.004, places=4)

  def test_reset_zeroes_filter(self):
    model = _good_model()
    self._run(model, offset=5.0, gain=1.0, iterations=200)
    self.assertNotEqual(self.trim.correction, 0.0)
    self.trim.reset()
    self.assertEqual(self.trim.correction, 0.0)

  def test_disable_mid_stream_resets(self):
    model = _good_model()
    self._run(model, offset=5.0, gain=1.0, iterations=200)
    self.assertNotEqual(self.trim.correction, 0.0)
    self._run(model, enabled=False, offset=5.0, gain=1.0, iterations=1)
    self.assertEqual(self.trim.correction, 0.0)

  # --- Model-position fallback / blend (the point of this class) ---

  def test_no_lanelines_still_applies_offset(self):
    # The scenario this exists for: center-stripe-only road, no lane line on the curbed side.
    # Bad detection must NOT zero out the trim -- the offset bias should still apply, riding on
    # the model's own path, exactly as if lane lines were centered and confident.
    no_lines = _no_lanelines_model()
    self._run(no_lines, offset=5.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=4)  # same ceiling as good lanelines

  def test_one_sided_laneline_still_applies_offset(self):
    # Only one ego line confidently detected -- min(probL, probR, width_tol) is dragged down by
    # the missing side, same as fully-missing lines.
    one_sided = _one_sided_model()
    self._run(one_sided, offset=5.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=4)

  def test_no_lanelines_zero_offset_no_correction(self):
    # No lanelines AND no user bias: target collapses to the model's own path, so there's truly
    # nothing to correct (not even a spurious pull toward a phantom lane center).
    no_lines = _no_lanelines_model()
    self._run(no_lines, offset=0.0, gain=1.0, iterations=50)
    self.assertAlmostEqual(self.trim.correction, 0.0, places=6)

  def test_confident_lanelines_pull_toward_laneline_center_even_with_zero_offset(self):
    # Lane center is offset from the model's current path (model drifted left of true center);
    # with full confidence and no user bias, the trim should still pull toward the laneline
    # center -- this is the "full centering" behavior confidence unlocks.
    model = _good_model(lane_center_y=2.0, model_y=0.0)  # model 2m left of true lane center
    self._run(model, offset=0.0, gain=1.0, iterations=500)
    self.assertGreater(self.trim.correction, 0.0)  # pulls right, toward center

  def test_low_confidence_ignores_laneline_center_offset(self):
    # Same lane-position error as above, but lines are unreliable -- with zero user bias the
    # trim must NOT invent a correction from a laneline center it shouldn't trust.
    unreliable = _good_model(lane_center_y=2.0, model_y=0.0, probs=(0.1, 0.1, 0.1, 0.1))
    self._run(unreliable, offset=0.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.0, places=6)

  def test_implausible_width_falls_back_to_model_position(self):
    # A width far outside anything the width-tolerance curve models still degrades confidence
    # smoothly (not a crash / hard reject) and the offset-only fallback still applies.
    weird_width = _good_model(width=15.0)
    self._run(weird_width, offset=5.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=4)

  def test_no_model_position_hard_resets(self):
    # Unlike laneline-only failures, a missing/invalid model.position leaves no baseline to
    # offset from at all -- this is the one case that still hard-resets to zero.
    broken = _Model(lane_lines=[_XY([], []), _XY([], []), _XY([], []), _XY([], [])],
                     probs=[0.9, 0.9, 0.9, 0.9],stds=[0.1, 0.1, 0.1, 0.1], pos_x=[], pos_y=[])
    self._run(broken, offset=5.0, gain=1.0, iterations=50)
    self.assertEqual(self.trim.correction, 0.0)

  # --- Hardening: guards restored from the reference implementation ---

  def test_narrow_lane_not_centered(self):
    # Two confident stripes 1.5 m apart (double-stripe repaint, gore-point paint) must NOT be
    # treated as a lane to center in: the width-tolerance low edge zeroes the laneline scale,
    # so with no user bias there is no correction at all.
    narrow = _good_model(lane_center_y=1.0, model_y=0.0, width=1.5)
    self._run(narrow, offset=0.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.0, places=6)

  def test_high_std_ignores_laneline_center(self):
    # High positional uncertainty (rain/glare: the model is sure lines exist but not where)
    # must drag centering authority to zero even when probabilities are high.
    blurry = _good_model(lane_center_y=2.0, model_y=0.0, stds=(0.1, 0.6, 0.1, 0.1))
    self._run(blurry, offset=0.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.0, places=6)

  def test_nan_offset_is_inert(self):
    # A corrupt float param must never reach the wire: NaN offset -> no correction, kappa_cmd
    # passes through untouched.
    result = self._run(_good_model(), kappa_cmd=0.01, offset=float("nan"), iterations=10)
    self.assertEqual(self.trim.correction, 0.0)
    self.assertEqual(result, 0.01)

  def test_nan_gain_is_inert(self):
    result = self._run(_good_model(), kappa_cmd=0.01, offset=0.3, gain=float("nan"), iterations=10)
    self.assertEqual(self.trim.correction, 0.0)
    self.assertEqual(result, 0.01)

  def test_nan_laneline_probability_does_not_poison_correction(self):
    # A single NaN laneline sample (e.g. a corrupt model frame) must not leak into min()/
    # np.interp() -- unlike the structural array checks above, NaN doesn't raise, so without an
    # explicit finiteness guard it silently corrupts confidence (and therefore the correction)
    # with a NaN that survives every later frame until a hard reset. Treat it the same as any
    # other untrustworthy laneline sample: fall back to the model-position blend, not NaN.
    nan_prob = _good_model(probs=(0.9, float("nan"), 0.9, 0.9))
    result = self._run(nan_prob, kappa_cmd=0.01, offset=0.3, iterations=10)
    self.assertFalse(np.isnan(self.trim.correction))
    self.assertFalse(np.isnan(result))

  def test_nan_laneline_std_does_not_poison_correction(self):
    nan_std = _good_model(stds=(0.1, float("nan"), 0.1, 0.1))
    result = self._run(nan_std, kappa_cmd=0.01, offset=0.3, iterations=10)
    self.assertFalse(np.isnan(self.trim.correction))
    self.assertFalse(np.isnan(result))

  def test_nan_laneline_probability_recovers_without_reset(self):
    # Converge under confident lanelines, take one NaN-probability frame, then confirm later
    # good frames recover on their own -- the fallback for a bad sample should behave like any
    # other low-confidence frame (self-healing), not latch like the pre-fix NaN corruption did
    # (which required a hard reset: lane change / disengage / human-turn).
    good = _good_model(lane_center_y=2.0, model_y=0.0)
    self._run(good, offset=0.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=3)

    nan_prob = _good_model(lane_center_y=2.0, model_y=0.0, probs=(0.9, float("nan"), 0.9, 0.9))
    self._run(nan_prob, offset=0.0, gain=1.0, iterations=1)
    self.assertFalse(np.isnan(self.trim.correction))

    self._run(good, offset=0.0, gain=1.0, iterations=500)
    self.assertFalse(np.isnan(self.trim.correction))
    self.assertAlmostEqual(self.trim.correction, 0.004, places=3)

  # --- Rate-of-change limit: smooths confidence transitions (merge lanes, lines dropping out) ---

  def test_correction_rate_limited_on_confidence_jump(self):
    # Converge to a strong positive correction under confident, off-center lane lines.
    centered_confident = _good_model(lane_center_y=2.0, model_y=0.0)
    self._run(centered_confident, offset=0.0, gain=1.0, iterations=500)
    before = self.trim.correction
    self.assertAlmostEqual(before, 0.004, places=3)

    # Lane lines vanish entirely in the very next frame (e.g. crossing into a too-wide merge
    # lane) while a negative user offset now drives the fallback target the opposite way -- a
    # large, instantaneous target swing (+0.004 -> -0.004 worth of target).
    no_lines = _no_lanelines_model(model_y=0.0)
    after = self.trim.update(0.0, no_lines, self.V_EGO, True, -5.0, 1.0, True, False)

    # The correction must not have snapped toward the new target -- bounded to roughly one
    # tick's worth of rate-of-change, regardless of how far the target actually moved.
    self.assertLessEqual(abs(after - before), _CORRECTION_ROC_PER_TICK + 1e-9)

  def test_correction_eventually_converges_despite_rate_limit(self):
    # The rate limit paces the transition but must not prevent it from completing.
    centered_confident = _good_model(lane_center_y=2.0, model_y=0.0)
    self._run(centered_confident, offset=0.0, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, 0.004, places=3)

    no_lines = _no_lanelines_model(model_y=0.0)
    self._run(no_lines, offset=-5.0, gain=1.0, iterations=1000)
    self.assertAlmostEqual(self.trim.correction, -0.004, places=3)

  def test_fallback_bias_is_position_independent_by_design(self):
    # Pins the fallback semantics deliberately: with no lanelines, error == offset regardless of
    # where the model path is (target moves with the baseline), i.e. the bias is a constant push,
    # not a position controller. If this ever changes, it should change on purpose.
    a = _no_lanelines_model(model_y=0.0)
    b = _no_lanelines_model(model_y=-3.0)
    self._run(a, offset=0.3, gain=1.0, iterations=500)
    correction_a = self.trim.correction
    self.trim.reset()
    self._run(b, offset=0.3, gain=1.0, iterations=500)
    self.assertAlmostEqual(self.trim.correction, correction_a, places=9)

  # --- Lanefull (enable_lane_full_mode_ang): off = the offset alone on the model's path ---

  def _trace(self, model, offset, lane_full=None, iterations=300):
    """The correction every frame from a fresh trim."""
    self.trim.reset()
    out = []
    for _ in range(iterations):
      self._run(model, offset=offset, lane_full=lane_full)
      out.append(self.trim.correction)
    return out

  def test_lanefull_off_is_the_untrusted_lines_result(self):
    # Whatever the lane lines say, Lanefull off steers exactly as if they couldn't be trusted (scale 0).
    off_path = {"clear, 2 m off the model's path": _good_model(lane_center_y=2.0, model_y=0.0),
                "partly trusted, 2 m off the model's path": _good_model(lane_center_y=2.0, model_y=0.0, probs=(0.9, 0.6, 0.6, 0.9))}
    lines = {**off_path, "one line": _one_sided_model(), "none": _no_lanelines_model()}
    for offset in (0.0, 0.3):
      untrusted = self._trace(_no_lanelines_model(), offset)
      for name, model in lines.items():
        with self.subTest(lines=name, offset=offset):
          self.assertEqual(self._trace(model, offset, lane_full=False), untrusted)
      for name, model in off_path.items():  # these lines do steer with Lanefull on, so the check above can fail
        with self.subTest(lines=name, offset=offset, lane_full=True):
          self.assertNotEqual(self._trace(model, offset), untrusted)

  def test_lanefull_off_zero_offset_no_correction(self):
    self._run(_good_model(lane_center_y=2.0, model_y=0.0), offset=0.0, lane_full=False, iterations=500)
    self.assertEqual(self.trim.correction, 0.0)

  def test_lanefull_off_keeps_the_offset(self):
    # Lanefull off drops the lane lines, not the trim: an offset still steers.
    self._run(_good_model(lane_center_y=2.0, model_y=0.0), offset=0.3, lane_full=False, iterations=500)
    self.assertGreater(self.trim.correction, 0.0)

  def test_lanefull_on_or_omitted_is_unchanged(self):
    for name, model in (("clear", _good_model(lane_center_y=2.0, model_y=0.0)), ("one line", _one_sided_model()),
                        ("none", _no_lanelines_model())):
      for offset in (0.0, 0.3):
        with self.subTest(lines=name, offset=offset):
          self.assertEqual(self._trace(model, offset, lane_full=True), self._trace(model, offset))
    # and on still centers on clear lines (pulls right toward the lane center with no offset)
    self.assertGreater(self._trace(_good_model(lane_center_y=2.0, model_y=0.0), 0.0, lane_full=True)[-1], 0.0)


class TestLaneFullSettingReachesTrim(unittest.TestCase):
  """enable_lane_full_mode_ang as the host publishes it, through LateralAngleExt to the trim."""

  def _correction(self, published):
    CP = CarInterface.get_non_essential_params(CAR.FORD_F_150_MK14)
    ext = LateralAngleExt(CP, InputTracker(CP, 0), SharedLateralState())
    params = {"enable_lane_positioning_ang": b"1", "custom_path_offset_ang": b"0.0", **published}
    ext.update_angle_params(ParamStore(params.items()))
    # confident lane lines centered 2 m right of the model's path, no lane change, no model curvature
    model = _good_model(lane_center_y=2.0, model_y=0.0)
    model.orientationRate = SimpleNamespace(z=[])
    model.meta = SimpleNamespace(laneChangeState=0, laneChangeDirection=0)
    ext.inputs.model = model
    CS = SimpleNamespace(out=SimpleNamespace(vEgoRaw=20.0, steeringPressed=False, steeringAngleDeg=0.0, yawRate=0.0))
    for _ in range(100):
      ext.update_angle_strategy(SimpleNamespace(latActive=True), CS, SimpleNamespace(curvature=0.0))
    return ext.lane_center_trim.correction

  def test_published_off_reaches_the_trim(self):
    self.assertEqual(self._correction({"enable_lane_full_mode_ang": b"0"}), 0.0)

  def test_missing_empty_or_unparsable_is_on(self):
    for published in ({}, {"enable_lane_full_mode_ang": b""}, {"enable_lane_full_mode_ang": b"junk"},
                      {"enable_lane_full_mode_ang": b"1"}):
      with self.subTest(published=published):
        self.assertGreater(self._correction(published), 0.0)

  def test_on_before_the_first_settings_frame(self):
    CP = CarInterface.get_non_essential_params(CAR.FORD_F_150_MK14)
    ext = LateralAngleExt(CP, InputTracker(CP, 0), SharedLateralState())
    self.assertIs(ext.enable_lane_full_mode_ang, True)
    ext.update_angle_params(None)  # no params this frame: the setting keeps its value
    self.assertIs(ext.enable_lane_full_mode_ang, True)


if __name__ == "__main__":
  unittest.main()
