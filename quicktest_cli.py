"""
QuickTest CLI - Phase 1 single-file prototype

Usage:
  - python quicktest_cli.py --init-sample   # create data/ and sample test case
  - python quicktest_cli.py --list          # list available test cases
  - python quicktest_cli.py --run "Title"   # run test case by title

This single-file prototype bundles basic models, storage, an interactive executor,
and simple evidence capture (screenshots). Everything is local and offline.

Dependencies (install locally):
  pip install pyautogui pillow

Note: pyautogui may require additional OS-specific packages. If unavailable, the
screenshot function will gracefully fall back to creating a small placeholder.

"""

import argparse
import json
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime
from itertools import filterfalse
from typing import List, Dict, Optional

# -----------------------------
# Configuration / Paths
# -----------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
EVIDENCE_DIR = os.path.join(BASE_DIR, "evidence")
CASES_FILE = os.path.join(DATA_DIR, "test_cases.json")
PLANS_FILE = os.path.join(DATA_DIR, "test_plans.json")
EXECUTIONS_FILE = os.path.join(DATA_DIR, "executions.json")

# -----------------------------
# Utilities
# -----------------------------

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

def now_iso():
    return datetime.now().isoformat()

# -----------------------------
# Models
# -----------------------------
@dataclass
class TestStep:
    description: str
    expected_result: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self):
        return asdict(self)


@dataclass
class TestCase:
    title: str
    steps: List[TestStep]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reusable: bool = False

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "reusable": self.reusable,
            "steps": [s.to_dict() for s in self.steps],
        }

@dataclass
class TestPlan:
    name: str
    test_case_ids: List[str]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self):
        return asdict(self)


# -----------------------------
# Storage
# -----------------------------

def get_items(kind):
    path = {"case": CASES_FILE, "plan": PLANS_FILE, "exec": EXECUTIONS_FILE}[kind]
    return load_json(path)

def save_items(kind, data):
    path = {"case": CASES_FILE, "plan": PLANS_FILE, "exec": EXECUTIONS_FILE}[kind]
    if kind == "exec":
        # Load existing executions
        existing = load_json(path) or []
        # Append the new execution record (single dict)
        existing.append(data)
        save_json(path, existing)
    else:
        # For cases and plans, we save the whole list (overwrite)
        save_json(path, data)

def load_json(path) -> Optional[List[Dict]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            if isinstance(data, dict):
                return [data]
            elif isinstance(data, list):
                return data
            else:
                return []
        except json.JSONDecodeError:
            return []


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# -----------------------------
# Evidence capture
# -----------------------------
try:
    import pyautogui
    from PIL import Image
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False


def take_screenshot(test_id: str, step_id: str) -> str:
    """Take a screenshot and return path. Falls back to placeholder if pyautogui missing."""
    run_folder = os.path.join(EVIDENCE_DIR, test_id)
    os.makedirs(run_folder, exist_ok=True)
    filename = f"{step_id}_{uuid.uuid4().hex}.png"
    path = os.path.join(run_folder, filename)

    if PYAUTOGUI_AVAILABLE:
        try:
            img = pyautogui.screenshot()
            img.save(path)
            return path
        except Exception as e:
            # graceful fallback
            print(f"Screenshot failed: {e}. Creating placeholder image.")

    # Fallback: create a tiny placeholder PNG
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (400, 200), (220, 220, 220, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 10), "placeholder screenshot", fill=(0, 0, 0))
        img.save(path)
        return path
    except Exception:
        # last resort: create an empty file
        with open(path, "wb") as f:
            f.write(b"")
        return path


# -----------------------------
# Executor (interactive)
# -----------------------------

def run_test_case_interactive(case_dict: Dict) -> Dict:
    """Run a test case in the terminal.

    Returns an execution record that can be saved.
    """
    tc_id = case_dict.get("id") or str(uuid.uuid4())
    title = case_dict.get("title", "<no-title>")

    print(f"\n=== Running test case: {title} ===")
    results = []

    for idx, step in enumerate(case_dict.get("steps", []), start=1):
        sid = step.get("id") or str(uuid.uuid4())
        print(f"\nStep {idx}: {step.get('description')}")
        print(f"Expected: {step.get('expected_result')}")

        # Wait for the tester to perform the action and then collect outcome
        user = input("Outcome (p=pass / f=fail / s=shot / r=record / q=quit): ").strip().lower()

        screenshot_path = None
        recording_path = None

        if user == "s":
            screenshot_path = take_screenshot(tc_id, sid)
            print(f"Saved screenshot: {screenshot_path}")
            # ask for final outcome after screenshot
            user = input("Result after screenshot (p/f): ").strip().lower()

        if user == "q":
            print("Aborting test run early.")
            results.append({"step": sid, "outcome": "aborted", "timestamp": now_iso()})
            break

        if user not in ("p", "f"):
            print("Unrecognised input - marking as fail.")
            user = "f"

        results.append({
            "step": sid,
            "outcome": "pass" if user == "p" else "fail",
            "screenshot": screenshot_path,
            "recording": recording_path,
            "timestamp": now_iso(),
        })

    exec_record = {
        "execution_id": str(uuid.uuid4()),
        "test_case_id": tc_id,
        "title": title,
        "started_at": now_iso(),
        "results": results,
    }

    save_items("exec", exec_record)
    print(f"\nExecution saved: {exec_record['execution_id']}")
    return exec_record

# -----------------------------
# Editing a Test Case
# -----------------------------
def edit_test_case_interactive(case_dict: Dict):
    title = case_dict.get("title")
    print(f"Editing test case: {title}.")
    user_action = input("Action: (R=Rename, E=Edit Test Steps, X=Exit)").strip().lower()

    if user_action == "r":
        cases = get_items("case") or []
        while True:
            renamed_title = input("New test case title: ").strip()
            if not renamed_title:
                print("Title cannot be empty.")
                return

            if is_new_test_case_title_unique(renamed_title, cases):
                # After editing, save updated title to file
                for c in cases:
                    if c.get("title") == title:
                        c["title"] = renamed_title
                        break
                save_items("case", cases)
                break
            # Otherwise, prompt again
            print("Please enter a unique title.\n")

    if user_action == "e":
        steps = case_dict.get("steps", [])
        if not steps:
            print("No steps found for this test case.")
            return

        while True:
            print("\nTest Steps:")
            for i, step in enumerate(steps, start=1):
                print(f"{i}. {step.get('description', '')}  -> Expected: {step.get('expected_result', '')}")

            choice = input(
                "\nEnter step number to edit.\n"
                "Press R to Reorder steps.\n"
                "Press A to Add a new step.\n"
                "Press C to Copy an exiting step.\n"
                "(or press Enter to finish): "
            ).strip().lower()

            #Choice is blank
            if not choice:
                break # break's execution.

            if choice == "r":
                if len(steps) > 1:
                    print("\nReorder steps:")
                    print("Current order:")
                    for i, step in enumerate(steps, start=1):
                        print(f"{i}. {step.get('description', '')}")

                    try:
                        old_index = int(input("Enter step number to move: ").strip()) - 1
                        if not (0 <= old_index < len(steps)):
                            print("Invalid source step number.")
                            continue
                        new_index = int(input("Enter new position number: ").strip()) - 1
                        if not (0 <= new_index < len(steps)):
                            print("Invalid destination position.")
                            continue

                        # Move the step
                        step_to_move = steps.pop(old_index)
                        steps.insert(new_index, step_to_move)

                        print(f"Moved step {old_index + 1} → {new_index + 1}.")
                    except ValueError:
                        print("Invalid input. Please enter numeric step positions.")
                else:
                    print("There must be more than 1 step in a test case to allow reordering.")
                continue  # Return to step menu

            #Add new step
            if choice == "a":
                steps = add_test_step_interactive(steps)
                continue

            #Copy Existing Test Step
            if choice == "c":
                steps = copy_test_step_interactive(steps)
                continue

            # From here on, handle step editing
            elif not choice.isdigit() or not (1 <= int(choice) <= len(steps)):
                print("Invalid choice. Please enter a valid step number.")
                continue

            step_index = int(choice) - 1
            step = steps[step_index]

            print(f"\nSelected Step {choice}:")
            print(f"Description: {step.get('description', '')}")
            print(f"Expected Result: {step.get('expected_result', '')}")

            edit_action = input("Edit (d=Description, e=Expected, b=Both, x=Cancel): ").strip().lower()
            if edit_action == "x":
                continue

            if edit_action in ("d", "b"):
                print(f"Current description: {step.get('description', '')}")
                new_desc = input("New description (leave blank to keep current): ").strip()
                if new_desc:
                    step["description"] = new_desc

            if edit_action in ("e", "b"):
                print(f"Current expected result: {step.get('expected_result', '')}")
                new_exp = input("New expected result (leave blank to keep current): ").strip()
                if new_exp:
                    step["expected_result"] = new_exp

            # Save back the modified step
            steps[step_index] = step

            print("\nStep updated.")
            cont = input("Edit another step? (y/n): ").strip().lower()
            if cont != "y":
                break

        # After editing/reordering, save updated steps to file
        cases = get_items("case") or []
        for c in cases:
            if c.get("title") == title:
                c["steps"] = steps
                break
        save_items("case", cases)
        print(f"Test case '{title}' updated successfully.")

        if user_action == "x":
            return

# -----------------------------
# Helpers: sample data creation
# -----------------------------

def create_sample_case():
    s1 = TestStep(description="Open the application", expected_result="The app opens and main window shows")
    s2 = TestStep(description="Login as test user", expected_result="Dashboard visible")
    s3 = TestStep(description="Navigate to Reports", expected_result="Reports page loads")
    tc = TestCase(title="Basic smoke: app start & reports", steps=[s1, s2, s3])
    save_items("case", [tc.to_dict()])
    print(f"Sample test case created: {tc.title}")


# -----------------------------
# CLI
# -----------------------------

def list_cases():
    cases = get_items("case") or []
    if not cases:
        print("No test cases found. Use --init-sample to create one.")
        return
    print("\nAvailable test cases:")
    for c in cases:
        print(f" - {c.get('title')}  (id: {c.get('id')})")


def run_by_title(titlep: str):
    matching_case = check_for_matching_test_case_by_title(titlep)
    if matching_case is not None:
        run_test_case_interactive(matching_case)

def edit_by_title(titlep: str):
    matching_case = check_for_matching_test_case_by_title(titlep)
    if matching_case is not None:
        edit_test_case_interactive(matching_case)

def check_for_matching_test_case_by_title(titlep: str):
    cases = get_items("case") or []
    title_lwr = titlep.strip().lower()
    match = None
    for c in cases:
        if c.get("title").lower() == title_lwr:
            match = c
            return match
    if not match:
        print(f"No test case with title '{title_lwr}' found.")
        return match

def show_executions():
    records = get_items("exec") or []
    if not records:
        print("No executions recorded yet.")
        return
    for r in records:
        print(f"Execution {r.get('execution_id')} - {r.get('title')} - started {r.get('started_at')}")
        for idx, res in enumerate(r.get('results', []), start=1):
            print(f"  Step {idx}: {res.get('outcome')}  screenshot: {res.get('screenshot')}")

def add_case_interactive():
    cases = get_items("case") or []

    while True:
        title = input("New test case title: ").strip()
        if not title:
            print("Title cannot be empty.")
            return

        if is_new_test_case_title_unique(title, cases):
            break
        # Otherwise, prompt again
        print("Please enter a unique title.\n")

    steps = []
    steps = add_test_step_interactive(steps)

    tc = TestCase(title=title, steps=[TestStep(**s) for s in steps])
    cases.append(tc.to_dict())
    save_items("case", cases)
    print(f"Saved test case '{title}'")

def add_test_step_interactive(steps):
    print("Enter steps (blank description to finish):")
    while True:
        desc = input(" Step description: ").strip()
        if not desc:
            break
        expected = input(" Expected result: ").strip()
        steps.append(TestStep(description=desc, expected_result=expected).to_dict())
        return steps

    if not steps:
        print("No steps added; aborting.")
        return steps

#def copy_test_step_interactive(steps): New code to implement.


def is_new_test_case_title_unique(new_title, cases):
    # Enforce unique title
    existing_titles = [c.get("title", "").strip().lower() for c in cases]
    if new_title.strip().lower() in existing_titles:
        print(f"A test case with the title '{new_title}' already exists. Please choose a unique name.")
        return False
    else:
        return True

def parse_args_and_run():
    parser = argparse.ArgumentParser(description="QuickTest CLI - local test runner")
    parser.add_argument("--init-sample", action="store_true", help="Create data folder and a sample test case")
    parser.add_argument("--list", action="store_true", help="List available test cases")
    parser.add_argument("--run", metavar='TITLE', help="Run a test case by title")
    parser.add_argument("--executions", action="store_true", help="Show past executions")
    parser.add_argument("--add", action="store_true", help="Interactively add a new test case")
    parser.add_argument("--edit", metavar='TITLE', help="Edit a test case by title")

    args = parser.parse_args()

    ensure_dirs()

    if args.init_sample:
        create_sample_case()
        return
    if args.list:
        list_cases()
        return
    if args.add:
        add_case_interactive()
        return
    if args.executions:
        show_executions()
        return
    if args.run:
        run_by_title(args.run)
        return
    if args.edit:
        edit_by_title(args.edit)
        return

    parser.print_help()


if __name__ == "__main__":
    parse_args_and_run()