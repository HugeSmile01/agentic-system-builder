#!/bin/bash
ACTION=$1
ID=$2
TASK=$3
FILE="local_tasks.txt"

touch "$FILE"

case $ACTION in
  list)
    cat "$FILE"
    ;;
  create)
    echo "$TASK" >> "$FILE"
    echo "Created: $TASK"
    ;;
  update)
    if [ -z "$ID" ]; then echo "ID required"; exit 1; fi
    sed -i "${ID}s/.*/$TASK/" "$FILE"
    echo "Updated ID $ID: $TASK"
    ;;
  delete)
    if [ -z "$ID" ]; then echo "ID required"; exit 1; fi
    sed -i "${ID}d" "$FILE"
    echo "Deleted ID $ID"
    ;;
  *)
    echo "Unknown action"
    ;;
esac
