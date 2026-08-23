@echo off
REM run_nfl.bat -- runs the full NFL data pipeline locally, end to end.
REM
REM Real step order confirmed against .github\workflows\scrape.yml's
REM "scrape" job (2026-08-23) -- NOT assumed from any prior summary.
REM Does NOT git add/commit/push anything (unlike the cloud job's final
REM step) -- this only regenerates local nfl\data\*.json /
REM nfl\data\fieldview.duckdb. Committing stays a separate manual step.
REM
REM Each step is echoed before it runs. A failed step is logged clearly
REM and the run continues to the next step rather than stopping, so one
REM broken scraper doesn't kill the rest of the pipeline.
REM
REM Env vars (e.g. any API keys individual scripts read) come from
REM whatever's already set in the environment -- nothing is read, set,
REM or hardcoded here.

setlocal enabledelayedexpansion
cd /d "%~dp0"
call fieldview_env\Scripts\activate.bat

set RESULTS_FILE=%TEMP%\fieldview_run_nfl_results.txt
if exist "%RESULTS_FILE%" del "%RESULTS_FILE%"
set FAIL_COUNT=0

echo ============================================
echo  NFL pipeline -- starting
echo ============================================

call :run_step "scrape_depth.py" "python nfl\scripts\scrape_depth.py"
call :run_step "scrape_otc.py" "python nfl\scripts\scrape_otc.py"
call :run_step "scrape_stats.py" "python nfl\scripts\scrape_stats.py"
call :run_step "scrape_madden.py" "python nfl\scripts\scrape_madden.py"
call :run_step "scrape_contracts_spotrac.py" "python nfl\scripts\scrape_contracts_spotrac.py"
call :run_step "build_db.py" "python nfl\scripts\build_db.py"
call :run_step "build_match.py" "python nfl\scripts\build_match.py"
call :run_step "export_master.py" "python nfl\scripts\export_master.py nfl\data\players_master.json"

echo.
echo ============================================
echo  NFL pipeline summary
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
