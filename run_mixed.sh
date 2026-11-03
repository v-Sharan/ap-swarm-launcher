uv run ap-sitl-swarm \
  --vehicle ./bin/arduplane:quadplane:10 \
  --vehicle ./bin/arducopter:quad:5 \
  --num-drones-per-row 5 --home 12.928852,80.046431 \
  --ip "192.168.31.15"