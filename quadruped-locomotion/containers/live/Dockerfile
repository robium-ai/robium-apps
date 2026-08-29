ARG ISAAC_LAB_IMAGE=nvcr.io/nvidia/isaac-lab:3.0.0-beta2-post1@sha256:ae9c938a16df856effad6dab92115ee0dce2a8813f56847eeeccbebc008d02c4
FROM ${ISAAC_LAB_IMAGE}

USER root
COPY . /opt/robium/quadruped-locomotion
RUN chmod 0755 /opt/robium/quadruped-locomotion/containers/live/entrypoint.sh

ENV ISAACLAB_ROOT=/workspace/isaaclab \
    ISAACLAB_LAUNCHER=/workspace/isaaclab/isaaclab.sh \
    ISAACLAB_CLI_STYLE=legacy \
    GO2_DATA_ROOT=/models/quadruped \
    GO2_TASK=Isaac-Velocity-Flat-Unitree-Go2-v0 \
    GO2_CHECKPOINT_ITERATION=1999 \
    GO2_ARCHIVE_SHA256=de11ce9711a400de005dddff4c6500a8d81e8ae9149016ca159abe563439477f \
    ACCEPT_EULA=Y \
    PRIVACY_CONSENT=Y

WORKDIR /opt/robium/quadruped-locomotion
EXPOSE 8888
ENTRYPOINT ["/opt/robium/quadruped-locomotion/containers/live/entrypoint.sh"]
