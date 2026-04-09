import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional, Literal

STATE_FILE = "pipeline_state.json"

class PipelineState:
    def __init__(self, session_year: int):
        self.session_year = session_year
        self.state_path = os.path.join(f"data/{session_year}rs", STATE_FILE)
        self._lock = threading.RLock()
        self.data = self._load_state()

    def _load_state(self) -> Dict:
        if os.path.exists(self.state_path):
            with open(self.state_path, 'r') as f:
                return json.load(f)
        return {}

    def save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, 'w') as f:
                json.dump(self.data, f, indent=2)

    def get_bill(self, bill_number: str) -> Dict:
        with self._lock:
            if bill_number not in self.data:
                now = datetime.now().isoformat()
                self.data[bill_number] = {
                    "first_seen": now,
                    "last_updated": now,
                    "last_seen": None,
                    "needs_download": True,
                    "needs_convert": False,
                    "needs_amend": False,
                    "needs_qa": False,
                    "files": {},
                    "qa_results": None,
                    "amended_status": "original", # original, amended, failed
                    "amend_input_hash": None,
                    "qa_input_hash": None
                }
            else:
                # Ensure existing bills have these fields for sorting compatibility
                bill = self.data[bill_number]
                if "first_seen" not in bill:
                    bill["first_seen"] = bill.get("last_seen") or datetime.now().isoformat()
                if "last_updated" not in bill:
                    bill["last_updated"] = bill.get("last_updated_local") or bill["first_seen"]

            return self.data[bill_number]

    def update_bill(self, bill_number: str, updates: Dict):
        with self._lock:
            bill = self.get_bill(bill_number)
            # Recursive update or simple merge
            for k, v in updates.items():
                if isinstance(v, dict) and k in bill and isinstance(bill[k], dict):
                    bill[k].update(v)
                else:
                    bill[k] = v
            self.data[bill_number]["last_updated_local"] = datetime.now().isoformat()
            self.save()

    def mark_dirty(self, bill_number: str, stage: Literal['download', 'convert', 'amend', 'qa']):
        """Cascading dirty marker"""
        stages = ['download', 'convert', 'amend', 'qa']
        start_idx = stages.index(stage)
        updates = {}
        for i in range(start_idx, len(stages)):
            key = f"needs_{stages[i]}"
            updates[key] = True
        self.update_bill(bill_number, updates)

    def clean_state(self, current_bill_numbers: list[str]):
        """Removes bills from state that are no longer in the master list."""
        with self._lock:
            initial_count = len(self.data)
            self.data = {k: v for k, v in self.data.items() if k in current_bill_numbers}
            removed_count = initial_count - len(self.data)
            if removed_count > 0:
                print(f"Removed {removed_count} orphaned records from state.")
                self.save()
