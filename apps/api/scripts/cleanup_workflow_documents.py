import json

from app.services.job_manager import job_manager


def main() -> int:
    result = job_manager.clean_workflow_documents()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
