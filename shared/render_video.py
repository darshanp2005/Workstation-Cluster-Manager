import argparse, time, os, random

p = argparse.ArgumentParser() #will handle command-line inputs.

p.add_argument("--frame", type=int, required=True)
args = p.parse_args()
print(f"Rendering frame {args.frame} on {os.uname().nodename} ...")
time.sleep(random.uniform(1.5, 4.0))
print(f"Frame {args.frame} completed.")

# This is a dummy workload generator:
# Takes a frame number as input.
# Pretends to “render” it (sleep for a few seconds).
# Reports which machine did the work.