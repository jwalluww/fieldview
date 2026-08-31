@echo off
REM run_epl.bat -- runs the full EPL data pipeline locally, end to end.
REM
REM Real step order confirmed by reading epl\scripts\ and shared\scripts\
REM directly (2026-08-29) -- there is no cloud job for EPL yet (CLAUDE.md:
REM manual/local only, no scrape.yml job, no prior orchestrator). Order:
REM scrape_fpl.py (writes epl\data\epl_players.json) and
REM shared\scripts\scrape_sofifa.py (writes epl\data\sofifa_epl.json, the
REM path build_epl_db.py actually reads) can both run first, independently
REM -- neither depends on the other's output. build_epl_db.py then loads
REM both JSON files straight into epl\data\fieldview.duckdb (one table per
REM source, no joins), build_epl_match.py does the name-based matching
REM (FPL base population vs sofifa_ratings), and export_epl_master.py
REM writes the final epl_players_master.json.
REM
REM scrape_sofifa.py takes CLI args (`<league_id> <output_path>`), unlike
REM every other sport's scrapers -- confirmed by reading its own __main__
REM block. EPL is league id 13 (MLS is 39, not used here). Output path is
REM epl\data\sofifa_epl.json specifically because that's the exact path
REM build_epl_db.py's load_sofifa_ratings() reads.
REM
REM Neither scrape_fpl.py nor scrape_sofifa.py reads any env vars
REM (confirmed by grepping both for os.environ/getenv -- no matches), so
REM there's nothing to read/set/hardcode here.
REM
REM Does NOT git add/commit/push anything -- this only regenerates local
REM epl\data\*.json / epl\data\fieldview.duckdb. Committing stays a
REM separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.

setlocal enabledelayedexpansion
cd /d "%~dp0"
call fieldview_env\Scripts\activate.bat

set RESULTS_FILE=%TEMP%\fieldview_run_epl_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  EPL pipeline -- starting
echo ============================================

call :run_step "scrape_fpl.py" "python epl\scripts\scrape_fpl.py"
call :run_step "scrape_sofifa.py" "python shared\scripts\scrape_sofifa.py 13 epl\data\sofifa_epl.json"
call :run_step "build_epl_db.py" "python epl\scripts\build_epl_db.py"
call :run_step "build_epl_match.py" "python epl\scripts\build_epl_match.py"
call :run_step "export_epl_master.py" "python epl\scripts\export_epl_master.py epl\data\epl_players_master.json"

echo.
echo ============================================
echo  EPL pipeline summary
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
