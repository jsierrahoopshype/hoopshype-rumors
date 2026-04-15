name: HoopsHype Wrapped — Daily Roundup

on:
  # Runs at 7:00 UTC = 9:00 Madrid (summer/CEST) or 8:00 Madrid (winter/CET)
  schedule:
    - cron: '0 7 * * *'

  # Also triggerable manually from GitHub Actions UI
  workflow_dispatch:
    inputs:
      hours:
        description: 'Hours to look back'
        required: false
        default: '24'
        type: choice
        options:
          - '12'
          - '24'
          - '48'
          - '72'
      skip_slack:
        description: 'Skip Slack posting'
        required: false
        default: 'false'
        type: boolean

env:
  MAX_MONTHLY_RUNS: 50

jobs:
  generate:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Check monthly run limit
        id: limit_check
        run: |
          MONTH_START=$(date -u +%Y-%m-01T00:00:00Z)
          REPO="${{ github.repository }}"
          TOKEN="${{ secrets.GITHUB_TOKEN }}"

          RUN_COUNT=$(curl -s \
            -H "Authorization: Bearer $TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/${REPO}/actions/workflows/daily-wrapped.yml/runs?created=>=${MONTH_START}&per_page=1" \
            | python3 -c "
          import sys, json
          try:
              data = json.load(sys.stdin)
              print(data.get('total_count', 0))
          except:
              print(0)
          ")

          echo "Runs this month so far: $RUN_COUNT / ${{ env.MAX_MONTHLY_RUNS }}"

          if [ "$RUN_COUNT" -ge "${{ env.MAX_MONTHLY_RUNS }}" ]; then
            echo "limit_reached=true" >> $GITHUB_OUTPUT
            echo "::warning::Monthly run limit of ${{ env.MAX_MONTHLY_RUNS }} reached. Skipping."
          else
            echo "limit_reached=false" >> $GITHUB_OUTPUT
          fi

      - name: Stop if limit reached
        if: steps.limit_check.outputs.limit_reached == 'true'
        run: |
          echo "### ⚠️ Monthly Run Limit Reached" >> $GITHUB_STEP_SUMMARY
          echo "This workflow has hit its limit of **${{ env.MAX_MONTHLY_RUNS }} runs** this month." >> $GITHUB_STEP_SUMMARY
          echo "It will resume automatically on the 1st of next month." >> $GITHUB_STEP_SUMMARY
          exit 0

      - name: Check out repo
        if: steps.limit_check.outputs.limit_reached == 'false'
        uses: actions/checkout@v4

      - name: Set up Python
        if: steps.limit_check.outputs.limit_reached == 'false'
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Set scope variables
        if: steps.limit_check.outputs.limit_reached == 'false'
        id: scope
        run: |
          HOURS="${{ github.event.inputs.hours || '24' }}"
          SKIP_SLACK="${{ github.event.inputs.skip_slack || 'false' }}"
          echo "hours=$HOURS" >> $GITHUB_OUTPUT
          echo "skip_slack=$SKIP_SLACK" >> $GITHUB_OUTPUT
          echo "filename=hoopshype_wrapped_$(date +%Y-%m-%d).html" >> $GITHUB_OUTPUT

      - name: Generate roundup
        if: steps.limit_check.outputs.limit_reached == 'false'
        env:
          HH_API_KEY:         ${{ secrets.HH_API_KEY }}
          ANTHROPIC_API_KEY:  ${{ secrets.ANTHROPIC_API_KEY }}
          SLACK_WEBHOOK_URL:  ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          SLACK_FLAG=""
          if [ "${{ steps.scope.outputs.skip_slack }}" = "true" ]; then
            SLACK_FLAG="--no-slack"
          fi

          python hoopshype_wrapped.py \
            --hours ${{ steps.scope.outputs.hours }} \
            --output ${{ steps.scope.outputs.filename }} \
            $SLACK_FLAG

      - name: Upload HTML as artifact
        if: steps.limit_check.outputs.limit_reached == 'false'
        uses: actions/upload-artifact@v4
        with:
          name: hoopshype-wrapped-${{ steps.scope.outputs.hours }}h-${{ github.run_id }}
          path: ${{ steps.scope.outputs.filename }}
          retention-days: 30

      - name: Print summary
        if: steps.limit_check.outputs.limit_reached == 'false'
        run: |
          echo "### 🏀 HoopsHype Wrapped" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "**Scope:** Last ${{ steps.scope.outputs.hours }} hours" >> $GITHUB_STEP_SUMMARY
          echo "**File:** \`${{ steps.scope.outputs.filename }}\`" >> $GITHUB_STEP_SUMMARY
          echo "Download the HTML from the Artifacts section above." >> $GITHUB_STEP_SUMMARY
