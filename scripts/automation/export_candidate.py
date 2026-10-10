"""Called by Codex to produce data for the clean publisher, without git push."""
import argparse
import base64
import json
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--status", choices=["ready", "checkpoint", "blocked"], required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    patch = b"" if args.status == "blocked" else subprocess.check_output(["git", "diff", "--cached", "--binary", "HEAD"])
    print(json.dumps({"task_id": args.task, "base_sha": base, "status": args.status,
                      "summary": args.summary, "patch_b64": base64.b64encode(patch).decode()}))


if __name__ == "__main__":
    main()
