@echo off
REM run_mlb.bat -- runs the full MLB data pipeline locally, end to end.
REM
REM Real step order confirmed by reading mlb\scripts\ directly (2026-08-23)
REM -- there is no mlb\PIPELINE.md and no cloud job for MLB (CLAUDE.md:
REM manual/local only). scrape_roster.py and scrape_stats.py each load
REM straight into mlb\data\fieldview.duckdb themselves (no separate
REM build_db.py step, unlike NFL/NBA) -- confirmed by reading both
REM scripts' __main__ blocks. scrape_ratings.py (theshowratings.com via
REM the ScraperAPI proxy) doesn't depend on the roster/stats tables
REM either (its join key is the mlbam_id embedded in each player's photo
REM URL, not a DB lookup), so its position in this order is for clarity,
REM not a real dependency.
REM
REM scrape_ratings.py deliberately exits non-zero (SystemExit(1)) if its
REM own single-page test doesn't clear the site's block, rather than
REM burning a full 30-team run against a block it already knows is up --
REM that's real, intentional behavior in the script itself, and this
REM orchestrator's fail-and-continue handling is what lets the rest of
REM the MLB pipeline finish normally when that happens.
REM
REM Does NOT git add/commit/push anything -- this only regenerates local
REM mlb\data\*.json / mlb\data\fieldview.duckdb. Committing stays a
REM separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.
REM
REM Env vars (SCRAPERAPI_KEY for scrape_ratings.py, read the same way the
REM script already reads it via os.environ) come from whatever's already
REM set in the environment -- nothing is read, set, or hardcoded here.

setlocal enabledelayedexpansion
cd /d "%~dp0"
call fieldview_env\Scripts\activate.bat

set RESULTS_FILE=%TEMP%\fieldview_run_mlb_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  MLB pipeline -- starting
echo ============================================

call :run_step "scrape_roster.py" "python mlb\scripts\scrape_roster.py"
call :run_step "scrape_stats.py" "python mlb\scripts\scrape_stats.py"
call :run_step "scrape_ratings.py" "python mlb\scripts\scrape_ratings.py"
call :run_step "build_mlb_match.py" "python mlb\scripts\build_mlb_match.py"
call :run_step "export_mlb_master.py" "python mlb\scripts\export_mlb_master.py mlb\data\mlb_players_master.json"

echo.
echo ============================================
echo  MLB pipeline summary
echo ============================================
type "%RESULTS_FILE%"
if %FAIL_COUNT% GTR 0 (
    echo.
    echo %FAIL_COUNT% step^(s^) FAILED -- see [FAIL] lines above.
) else (
    echo.
    echo All steps completed successfully.
)

endlocal & exit /b %FAIL_COUNT%

:run_step
set "STEP_NAME=%~1"
set "STEP_CMD=%~2"
echo.
echo --- Running %STEP_NAME% ---
echo     %STEP_CMD%
%STEP_CMD%
if errorlevel 1 (
    echo [FAIL] %STEP_NAME%>>"%RESULTS_FILE%"
    echo     ^>^> %STEP_NAME% FAILED
    set /a FAIL_COUNT+=1
) else (
    echo [PASS] %STEP_NAME%>>"%RESULTS_FILE%"
    echo     ^>^> %STEP_NAME% OK
)
goto :eof
