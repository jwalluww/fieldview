@echo off
REM run_nba.bat -- runs the full NBA data pipeline locally, end to end.
REM
REM Real step order confirmed against nba\PIPELINE.md's "Execution order"
REM section and .github\workflows\scrape.yml's "scrape-nba" job
REM (2026-08-23) -- NOT assumed from any prior summary.
REM
REM fetch_stats.py IS included here (unlike scrape.yml's cloud job, which
REM has it commented out) -- CLAUDE.md and PIPELINE.md both confirm
REM stats.nba.com blocks the hosted GitHub Actions runner's IP but works
REM fine locally, and this script is documented as "runs locally/manually
REM only." A local orchestrator is exactly that context.
REM
REM scrape_2kratings.py is still the real daily-trickle scraper (3 random
REM teams/run against its own rolling pool state file) -- running it here
REM does one more trickle pass, not a full 30-team pull. That's its real
REM current behavior, not a limitation of this orchestrator.
REM
REM Does NOT git add/commit/push anything (unlike the cloud job's final
REM step) -- this only regenerates local nba\data\*.json /
REM nba\data\fieldview.duckdb. Committing stays a separate manual step.
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

set RESULTS_FILE=%TEMP%\fieldview_run_nba_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  NBA pipeline -- starting
echo ============================================

call :run_step "fetch_stats.py" "python nba\scripts\fetch_stats.py"
call :run_step "scrape_contracts_spotrac.py" "python nba\scripts\scrape_contracts_spotrac.py"
call :run_step "scrape_2kratings.py" "python nba\scripts\scrape_2kratings.py"
call :run_step "scrape_nbadepthcharts.py" "python nba\scripts\scrape_nbadepthcharts.py"
call :run_step "build_nba_db.py" "python nba\scripts\build_nba_db.py"
call :run_step "build_nba_match.py" "python nba\scripts\build_nba_match.py"
call :run_step "export_nba_master.py" "python nba\scripts\export_nba_master.py nba\data\nba_players_master.json"

echo.
echo ============================================
echo  NBA pipeline summary
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
