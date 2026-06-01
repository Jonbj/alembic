#!/bin/bash
# Auto-generated tournament sequence script
# Run this script to step through each model in the tournament

echo "=== Model Tournament Sequence ==="
echo "Total models: 3"
echo ""
echo "For each model:"
echo "  1. Switch to the model (/model <name>)"
echo "  2. Enter the worktree directory"
echo "  3. Ask Claude to implement the plan in .claude/tournament-prompt.md"
echo "  4. Press ENTER when ready to collect metrics and move to the next model"
echo ""
read -p "Press ENTER to start..." dummy
echo ""
echo "===== MODEL 1/3: sonnet ====="
echo "Worktree: .worktrees/tournament-sonnet"
echo ""
echo "/model sonnet"
echo "cd .worktrees/tournament-sonnet"
echo "# Ask Claude to implement the plan in .claude/tournament-prompt.md"
echo ""
echo "After implementation, run: python ../../scripts/model_tournament.py collect"
echo ""
read -p "Press ENTER when ready to collect metrics and continue..." dummy
echo ""
# Auto-collect from sonnet
(cd .worktrees/tournament-sonnet && python ../../scripts/model_tournament.py collect)
echo ""
echo "===== MODEL 2/3: opus ====="
echo "Worktree: .worktrees/tournament-opus"
echo ""
echo "/model opus"
echo "cd .worktrees/tournament-opus"
echo "# Ask Claude to implement the plan in .claude/tournament-prompt.md"
echo ""
echo "After implementation, run: python ../../scripts/model_tournament.py collect"
echo ""
read -p "Press ENTER when ready to collect metrics and continue..." dummy
echo ""
# Auto-collect from opus
(cd .worktrees/tournament-opus && python ../../scripts/model_tournament.py collect)
echo ""
echo "===== MODEL 3/3: qwen3.5:cloud ====="
echo "Worktree: .worktrees/tournament-qwen3.5-cloud"
echo ""
echo "/model qwen3.5:cloud"
echo "cd .worktrees/tournament-qwen3.5-cloud"
echo "# Ask Claude to implement the plan in .claude/tournament-prompt.md"
echo ""
echo "After implementation, run: python ../../scripts/model_tournament.py collect"
echo ""
read -p "Press ENTER when ready to collect metrics and continue..." dummy
echo ""
# Auto-collect from qwen3.5:cloud
(cd .worktrees/tournament-qwen3.5-cloud && python ../../scripts/model_tournament.py collect)
echo ""
echo "===== TOURNAMENT COMPLETE ====="
echo "Generating final report..."
python scripts/model_tournament.py report
echo ""
echo "Report generated: model_tournament_report.md"
echo ""
echo "To clean up: python scripts/model_tournament.py cleanup"
