@echo off
REM run_all.bat -- runs all six sports' pipelines locally, in sequence:
REM run_nfl.bat, run_nba.bat, run_mlb.bat, run_nhl.bat, run_epl.bat,
REM run_mls.bat. Each is fully self-contained (sets its own cwd/venv), so
REM this file just calls them and aggregates their results into one final
REM summary.
REM
REM Does NOT git add/commit/push anything, same as each individual
REM run_<sport>.bat. Committing stays a separate manual step so nothing
REM gets published without a look first.
REM
REM A sport whose pipeline has failed steps does NOT stop the rest of
REM this run -- each run_<sport>.bat already continues past its own
REM failed steps, and this file continues to the next sport regardless
REM of the previous sport's result, for the same reason.

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ################################################
echo  FieldView -- full pipeline run (all 6 sports)
echo ################################################

call "%~dp0run_nfl.bat"
set NFL_FAILS=%errorlevel%

call "%~dp0run_nba.bat"
set NBA_FAILS=%errorlevel%

call "%~dp0run_mlb.bat"
set MLB_FAILS=%errorlevel%

call "%~dp0run_nhl.bat"
set NHL_FAILS=%errorlevel%

call "%~dp0run_epl.bat"
set EPL_FAILS=%errorlevel%

call "%~dp0run_mls.bat"
set MLS_FAILS=%errorlevel%

set /a TOTAL_FAILS=NFL_FAILS+NBA_FAILS+MLB_FAILS+NHL_FAILS+EPL_FAILS+MLS_FAILS

echo.
echo ################################################
echo  FINAL SUMMARY -- all sports
echo ################################################

call :print_sport_summary "NFL" %NFL_FAILS% "%TEMP%\fieldview_run_nfl_results.txt"
call :print_sport_summary "NBA" %NBA_FAILS% "%TEMP%\fieldview_run_nba_results.txt"
call :print_sport_summary "MLB" %MLB_FAILS% "%TEMP%\fieldview_run_mlb_results.txt"
call :print_sport_summary "NHL" %NHL_FAILS% "%TEMP%\fieldview_run_nhl_results.txt"
call :print_sport_summary "EPL" %EPL_FAILS% "%TEMP%\fieldview_run_epl_results.txt"
call :print_sport_summary "MLS" %MLS_FAILS% "%TEMP%\fieldview_run_mls_results.txt"

echo.
if %TOTAL_FAILS% GTR 0 (
    echo TOTAL: %TOTAL_FAILS% step^(s^) failed across all sports -- see [FAIL] lines above.
) else (
    echo TOTAL: all steps, all sports, completed successfully.
)

endlocal & exit /b %TOTAL_FAILS%

:print_sport_summary
set "SPORT_NAME=%~1"
set "SPORT_FAILS=%~2"
set "SPORT_RESULTS=%~3"
echo.
if "%SPORT_FAILS%"=="0" (
    echo %SPORT_NAME%: all steps OK
) else (
    echo %SPORT_NAME%: %SPORT_FAILS% step^(s^) FAILED
)
if exist "%SPORT_RESULTS%" (
    for /f "usebackq delims=" %%L in ("%SPORT_RESULTS%") do echo     %%L
)
goto :eof
