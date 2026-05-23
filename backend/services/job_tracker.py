import os
import json
import sqlite3
import tempfile
import logging
from datetime import datetime
from services.database import DatabaseClient

class JobTracker:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(JobTracker, cls).__new__(cls, *args, **kwargs)
            cls._instance._init_tracker()
        return cls._instance
        
    def _init_tracker(self):
        self.is_sql_server = False
        self.table_name = "jobs"
        self.sqlite_db_path = os.path.join(tempfile.gettempdir(), "summitos_jobs.db")
        
        # Test connection to central SQL Server
        conn = None
        try:
            db = DatabaseClient()
            conn = db.get_connection()
            if conn:
                self.is_sql_server = True
                self.table_name = "Rides.BackgroundJobs"
                logging.info("JobTracker: Successfully connected to central SQL Server. Enabling shared job tracking.")
        except Exception as e:
            logging.warning(f"JobTracker: Could not connect to SQL Server, falling back to local SQLite: {e}")
            
        if conn:
            try:
                conn.close()
            except:
                pass
                
        if not self.is_sql_server:
            logging.info(f"JobTracker: Initialized with SQLite persistence at: {self.sqlite_db_path}")
            
        self._create_table()
        
    def _get_connection(self):
        if self.is_sql_server:
            try:
                db = DatabaseClient()
                conn = db.get_connection()
                if conn:
                    return conn
            except Exception as e:
                logging.error(f"JobTracker: Connection to SQL Server lost, degrading on-the-fly to SQLite: {e}")
                
            # Degradation fallback
            self.is_sql_server = False
            self.table_name = "jobs"
            self._create_table()
            
        conn = sqlite3.connect(self.sqlite_db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_table(self):
        conn = self._get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            if self.is_sql_server:
                cursor.execute(f"""
                    IF OBJECT_ID('{self.table_name}', 'U') IS NULL
                    CREATE TABLE {self.table_name} (
                        job_id NVARCHAR(100) PRIMARY KEY,
                        operation NVARCHAR(100) NOT NULL,
                        target_path NVARCHAR(500),
                        status NVARCHAR(50) NOT NULL,
                        logs NVARCHAR(MAX) NOT NULL,
                        created_at NVARCHAR(100) NOT NULL,
                        started_at NVARCHAR(100),
                        completed_at NVARCHAR(100),
                        duration_ms INT,
                        error NVARCHAR(MAX),
                        result NVARCHAR(MAX)
                    )
                """)
                conn.commit()
            else:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        job_id TEXT PRIMARY KEY,
                        operation TEXT NOT NULL,
                        target_path TEXT,
                        status TEXT NOT NULL,
                        logs TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        duration_ms INTEGER,
                        error TEXT,
                        result TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            logging.error(f"Error creating jobs table: {e}")
        finally:
            conn.close()
            
    def create_job(self, operation: str, target_path: str = None) -> str:
        import uuid
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        
        # B1: queued is the initial state
        initial_log = f"> Initializing background job {job_id} for {operation}..."
        logs_json = json.dumps([initial_log])
        
        conn = self._get_connection()
        if not conn:
            return job_id
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                INSERT INTO {self.table_name} (job_id, operation, target_path, status, logs, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, operation, target_path, "queued", logs_json, now_str)
            )
            conn.commit()
            
            # B4: Emit structured log for job_created
            logging.info(json.dumps({
                "event": "job_created",
                "jobId": job_id,
                "operation": operation,
                "targetPath": target_path,
                "status": "queued",
                "timestamp": now_str
            }))
            
        except Exception as e:
            logging.error(f"Error persisting job creation for {job_id}: {e}")
        finally:
            conn.close()
            
        return job_id
        
    def get_job(self, job_id: str) -> dict:
        conn = self._get_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                if self.is_sql_server:
                    columns = [column[0] for column in cursor.description]
                    row_dict = dict(zip(columns, row))
                else:
                    row_dict = dict(row)
                    
                logs = json.loads(row_dict["logs"])
                result = json.loads(row_dict["result"]) if row_dict.get("result") else None
                
                # C2 Standard Schema mapping
                return {
                    "jobId": row_dict["job_id"],
                    "operation": row_dict["operation"],
                    "targetPath": row_dict["target_path"],
                    "status": row_dict["status"],
                    "logs": logs,
                    "created_at": row_dict["created_at"],
                    "startedAt": row_dict["started_at"],
                    "finishedAt": row_dict["completed_at"],
                    "durationMs": row_dict["duration_ms"],
                    "errorType": "ExecutionError" if row_dict.get("error") else None,
                    "message": row_dict.get("error") if row_dict.get("error") else (logs[-1] if logs else None),
                    "result": result
                }
        except Exception as e:
            logging.error(f"Error retrieving job {job_id}: {e}")
        finally:
            conn.close()
        return None
        
    def start_job(self, job_id: str):
        now_str = datetime.now().isoformat()
        conn = self._get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return
                
            if self.is_sql_server:
                columns = [column[0] for column in cursor.description]
                row_dict = dict(zip(columns, row))
            else:
                row_dict = dict(row)
                
            logs = json.loads(row_dict["logs"])
            logs.append(f"> Background execution started for {row_dict['operation']}.")
            logs_json = json.dumps(logs)
            
            cursor.execute(
                f"""
                UPDATE {self.table_name} 
                SET status = ?, started_at = ?, logs = ?
                WHERE job_id = ?
                """,
                ("running", now_str, logs_json, job_id)
            )
            conn.commit()
            
            # B4: Emit structured log for job_started
            logging.info(json.dumps({
                "event": "job_started",
                "jobId": job_id,
                "operation": row_dict["operation"],
                "targetPath": row_dict["target_path"],
                "status": "running",
                "timestamp": now_str
            }))
            
        except Exception as e:
            logging.error(f"Error starting job {job_id}: {e}")
        finally:
            conn.close()
 
    def update_job_progress(self, job_id: str, status: str, new_logs: list = None, error: str = None, result: dict = None):
        now_str = datetime.now().isoformat()
        conn = self._get_connection()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {self.table_name} WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if not row:
                return
                
            if self.is_sql_server:
                columns = [column[0] for column in cursor.description]
                row_dict = dict(zip(columns, row))
            else:
                row_dict = dict(row)
                
            logs = json.loads(row_dict["logs"])
            if new_logs:
                logs.extend(new_logs)
            logs_json = json.dumps(logs)
            
            started_at = row_dict["started_at"]
            duration_ms = None
            if started_at:
                try:
                    start_dt = datetime.fromisoformat(started_at)
                    now_dt = datetime.fromisoformat(now_str)
                    duration_ms = int((now_dt - start_dt).total_seconds() * 1000)
                except Exception:
                    pass
            
            result_json = json.dumps(result) if result else (row_dict["result"] if row_dict.get("result") else None)
            
            if status in ["completed", "failed"]:
                cursor.execute(
                    f"""
                    UPDATE {self.table_name} 
                    SET status = ?, logs = ?, error = ?, result = ?, completed_at = ?, duration_ms = ?
                    WHERE job_id = ?
                    """,
                    (status, logs_json, error, result_json, now_str, duration_ms, job_id)
                )
            else:
                cursor.execute(
                    f"""
                    UPDATE {self.table_name} 
                    SET status = ?, logs = ?, error = ?, result = ?
                    WHERE job_id = ?
                    """,
                    (status, logs_json, error, result_json, job_id)
                )
            conn.commit()
            
            # B4: Emit structured log for job progression/completion/failure
            event_name = "job_progress"
            if status == "completed":
                event_name = "job_completed"
            elif status == "failed":
                event_name = "job_failed"
                
            logging.info(json.dumps({
                "event": event_name,
                "jobId": job_id,
                "operation": row_dict["operation"],
                "targetPath": row_dict["target_path"],
                "status": status,
                "durationMs": duration_ms,
                "error": error,
                "timestamp": now_str,
                "resultSummary": f"Result with keys: {list(result.keys())}" if result else None
            }))
            
        except Exception as e:
            logging.error(f"Error updating job progress for {job_id}: {e}")
        finally:
            conn.close()
