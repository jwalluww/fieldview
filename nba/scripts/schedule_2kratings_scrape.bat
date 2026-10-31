@echo off
REM RETIRED 2026-10-31: 2K ratings now come from nba2kapi in the cloud job (scrape_nba2kapi.py); scrape_2kratings.py is retired and re-scraping 2kratings.com here overwrote API-sourced rows in nba_ratings_2k.json.
REM This file is intentionally a no-op so a Task Scheduler job that still
REM points at it cannot overwrite the cloud pipeline's committed files.
REM The original steps are kept below, unreachable. Disable the Task
REM Scheduler job; do not delete this file.
exit /b 0

REM nba/scripts/schedule_2kratings_scrape.bat
REM
REM Intended to be run once daily by a Windows Task Scheduler task
REM pointed at this .bat file -- NOT registered automatically by
REM anything in this repo. See the schtasks command in the comment
REM block at the bottom of scrape_2kratings.py to register it yourself.
REM
REM Adds a random 0-30 minute delay before running the scraper, so the
REM actual scrape time still drifts day to day even though the
REM scheduled trigger itself fires at a fixed clock time (schtasks'
REM basic CLI has no native random-delay trigger option).

setlocal enabledelayedexpansion
set /a DELAY_SECONDS=%RANDOM% * 1800 / 32768
echo [%date% %time%] Waiting %DELAY_SECONDS%s before running NBA 2K ratings scrape...
timeout /t %DELAY_SECONDS% /nobreak >nul

cd /d C:\Users\wallj\DS_Projects\fieldview
call fieldview_env\Scripts\activate.bat
python nba\scripts\scrape_2kratings.py

endlocal
