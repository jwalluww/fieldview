@echo off
REM run_nhl.bat -- runs the full NHL data pipeline locally, end to end.
REM
REM Real step order confirmed by reading nhl\scripts\ directly (2026-08-23,
REM cloud-job note updated 2026-08-31) -- there is no nhl\PIPELINE.md, but
REM a real scrape-nhl job in .github\workflows\scrape.yml IS confirmed
REM running successfully in the cloud (as of 2026-08-25), now including
REM scrape_ratings.py too (moved into the cloud job 2026-08-31, see below):
REM scrape_roster.py -> scrape_stats.py -> scrape_ratings.py ->
REM build_nhl_match.py -> export_nhl_master.py. This script is the local/
REM manual counterpart for the same full end-to-end run -- not the only
REM way the pipeline runs, one of two places it can run from.
REM
REM scrape_roster.py and scrape_stats.py each load straight into
REM nhl\data\fieldview.duckdb themselves (no separate build_db.py step,
REM same pattern as MLB) -- confirmed by reading both scripts.
REM scrape_ratings.py genuinely DOES depend on scrape_roster.py
REM having already run -- it queries the nhl_roster table directly
REM (SELECT player_id, first_name, last_name, team_abbr FROM nhl_roster)
REM to build its name-matching index, since nhlratings.net has no clean
REM numeric join key the way MLB's photo URLs do. Roster must run first.
REM
REM scrape_ratings.py now pulls all 32 teams every run via ScraperAPI
REM (fixed 2026-08-31 -- the block was a static per-IP WAF rule, not a
REM TLS-fingerprint or cloud-vs-residential issue, so ScraperAPI's proxy
REM pool clears it same as it does for MLB). The old daily-trickle design
REM (3 random teams/run, local-only) is gone -- this is a full run every
REM time now, same shape as MLB's ratings scraper. build_nhl_match.py
REM joins nhl_ratings in automatically if the table exists, and ships
REM without it otherwise, so a rare fully-blocked run here still doesn't
REM break the rest of the pipeline.
REM
REM Does NOT git add/commit/push anything -- this only regenerates local
REM nhl\data\*.json / nhl\data\fieldview.duckdb. Committing stays a
REM separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.
REM
REM Env vars come from whatever's already set in the environment --
REM nothing is read, set, or hardcoded here.

setlocal enabledelayedexpansion
cd /d "%~dp0"
call fieldview_env\Scripts\activate.bat

set RESULTS_FILE=%TEMP%\fieldview_run_nhl_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  NHL pipeline -- starting
echo ============================================

call :run_step "scrape_roster.py" "python nhl\scripts\scrape_roster.py"
call :run_step "scrape_stats.py" "python nhl\scripts\scrape_stats.py"
call :run_step "scrape_ratings.py" "python nhl\scripts\scrape_ratings.py"
call :run_step "build_nhl_match.py" "python nhl\scripts\build_nhl_match.py"
call :run_step "export_nhl_master.py" "python nhl\scripts\export_nhl_master.py nhl\data\nhl_players_master.json"

echo.
echo ============================================
echo  NHL pipeline summary
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
