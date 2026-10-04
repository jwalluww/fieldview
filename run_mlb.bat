@echo off
REM run_mlb.bat -- runs the full MLB data pipeline locally, end to end.
REM
REM Real step order confirmed by reading mlb\scripts\ directly (2026-08-23)
REM -- there is no mlb\PIPELINE.md and no cloud job for MLB (CLAUDE.md:
REM manual/local only). scrape_roster.py and scrape_stats.py each load
REM straight into mlb\data\fieldview.duckdb themselves (no separate
REM build_db.py step, unlike NFL/NBA) -- confirmed by reading both
REM scripts' __main__ blocks. scrape_show_api.py (MLB The Show's official API via
REM plain requests; it replaced theshowratings.com + ScraperAPI, whose scrape_ratings.py
REM is retired) writes mlb\data\show_api_live.json + ratings_meta.json for
REM build_mlb_match.py. On a failed fetch it keeps the previous snapshot and exits 0.
REM
REM Does NOT git add/commit/push anything -- this only regenerates local
REM mlb\data\*.json / mlb\data\fieldview.duckdb. Committing stays a
REM separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.
REM
REM No env vars are needed (MLB ratings no longer use ScraperAPI).

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
call :run_step "scrape_show_api.py" "python mlb\scripts\scrape_show_api.py"
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
