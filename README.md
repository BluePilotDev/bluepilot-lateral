# BluePilot lateral

BluePilot's Ford lateral control as a library an opendbc fork mounts at `opendbc/bluepilot_lateral/`: both modes (curvature and angle), the CAN messages that carry them, the panda safety that checks them, and a settings manifest.

**This is a modified Ford safety model.** The panda safety allows signals and ranges that upstream's Ford safety blocks. A fork chooses whether to ship it.

**Status:** `v0.1.1`. It runs on bp-sunnypilot, a sunnypilot fork, through BluePilotDev/opendbc (sunnypilot's opendbc plus the hooks). IQPilot is next: its hooks and CI are in this repo, and its PR is in progress.

- [FORKS.md](FORKS.md): how a fork gets BluePilot lateral, the two supported ways to carry it (a submodule or a stamped copy made with `tools/vendor.sh`), and adding a fork.
- [HOSTS.md](HOSTS.md): what a host provides, the hook patch, and how to run the tests.
- [can/LANE_ASSIST_DATA1.md](can/LANE_ASSIST_DATA1.md): the Lane_Assist_Data1 bits angle mode uses.
- [CREDITS.md](CREDITS.md) and [LICENSE](LICENSE) (MIT).

History before 2026-09-15 lives in [BluePilotDev/bluepilot](https://github.com/BluePilotDev/bluepilot).
