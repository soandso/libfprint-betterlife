#!/bin/bash
for i in 1 2 3; do echo "--- verify $i: TOUCH RIGHT INDEX"; timeout 40 fprintd-verify dave 2>&1 | grep -E "Verify result"; sleep 1; done; echo DONE
