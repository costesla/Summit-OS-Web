
import subprocess
import json
import sys

def update_logic_app():
    rid = "/subscriptions/78c94919-e706-4356-9644-b00b4ecb43ad/resourceGroups/summit-sync-blob-processor_group/providers/Microsoft.Logic/workflows/summit-sync-blob-processor"
    
    print(f"Fetching current definition for {rid}...")
    try:
        raw = subprocess.check_output(["az", "logic", "workflow", "show", "--id", rid], stderr=subprocess.STDOUT)
        d = json.loads(raw)
    except Exception as e:
        print(f"Error fetching workflow: {e}")
        return

    # Update the folderId
    trigger_name = "When_a_blob_is_added_or_modified_(properties_only)_(V2)"
    if trigger_name in d["definition"]["triggers"]:
        print("Found trigger. Updating folderId to /function-releases...")
        d["definition"]["triggers"][trigger_name]["inputs"]["queries"]["folderId"] = "/function-releases"
    else:
        print(f"Error: Trigger {trigger_name} not found in definition.")
        print("Available triggers:", list(d["definition"]["triggers"].keys()))
        return

    # Write definition to temp file to avoid CLI quoting issues
    with open("new_definition.json", "w") as f:
        json.dump(d["definition"], f)

    print("Pushing updated definition via az resource update...")
    try:
        # Use @path to read from file
        subprocess.run([
            "az", "resource", "update", "--id", rid, 
            "--set", "properties.definition=@new_definition.json"
        ], check=True)
        print("Logic App successfully updated!")
    except Exception as e:
        print(f"Error updating resource: {e}")

if __name__ == "__main__":
    update_logic_app()
