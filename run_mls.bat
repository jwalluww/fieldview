@echo off
REM run_mls.bat -- runs the full MLS data pipeline locally, end to end.
REM
REM Real step order confirmed by reading mls\scripts\ and shared\scripts\
REM directly (2026-08-29) -- there is no cloud job for MLS yet (CLAUDE.md:
REM manual/local only, no scrape.yml job, no prior orchestrator). Order:
REM scrape_espn_roster.py (Phase 1a, writes mls\data\mls_roster.json),
REM fetch_asa_stats.py (Phase 1b, writes mls\data\mls_asa_stats.json), and
REM shared\scripts\scrape_sofifa.py (writes mls\data\mls_sofifa.json, the
REM exact path build_mls_match.py's SOFIFA_PATH reads) can all run first,
REM independently -- none of the three depends on either of the others'
REM output. build_mls_match.py (Phase 2) then reads all three JSON files
REM directly and writes mls\data\mls_player_match.json, and
REM export_mls_master.py (Phase 3) writes the final
REM mls_players_master.json.
REM
REM Confirmed MLS has NO separate DB-build step, unlike EPL --
REM build_mls_match.py's own docstring says so explicitly ("this script
REM has no DuckDB layer (unlike EPL) -- per spec, reads/writes JSON
REM directly, no build_mls_db.py step"), and no build_mls_db.py file
REM exists in mls\scripts\ at all. Confirmed, not assumed from MLB's
REM similar no-DB-step shape.
REM
REM scrape_sofifa.py takes CLI args (`<league_id> <output_path>`), same
REM shared script EPL uses -- confirmed by reading its own __main__ block.
REM MLS is league id 39 (EPL is 13, not used here). Output path is
REM mls\data\mls_sofifa.json specifically because that's the exact path
REM build_mls_match.py's SOFIFA_PATH constant reads.
REM
REM None of scrape_espn_roster.py, fetch_asa_stats.py, or
REM shared\scripts\scrape_sofifa.py reads any env vars (confirmed by
REM grepping mls\scripts\*.py and shared\scripts\*.py for
REM os.environ/getenv -- no matches), so there's nothing to read/set/
REM hardcode here.
REM
REM Does NOT git add/commit/push anything -- this only regenerates local
REM mls\data\*.json. Committing stays a separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.

setlocal enabledelayedexpansion
cd /d "%~dp0"
call fieldview_env\Scripts\activate.bat

set RESULTS_FILE=%TEMP%\fieldview_run_mls_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  MLS pipeline -- starting
echo ============================================

call :run_step "scrape_espn_roster.py" "python mls\scripts\scrape_espn_roster.py"
call :run_step "fetch_asa_stats.py" "python mls\scripts\fetch_asa_stats.py"
call :run_step "scrape_sofifa.py" "python shared\scripts\scrape_sofifa.py 39 mls\data\mls_sofifa.json"
call :run_step "build_mls_match.py" "python mls\scripts\build_mls_match.py"
call :run_step "export_mls_master.py" "python mls\scripts\export_mls_master.py mls\data\mls_players_master.json"

echo.
echo ============================================
echo  MLS pipeline summary
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
