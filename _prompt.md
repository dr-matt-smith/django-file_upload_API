there is a problem with this project

it does UNZIP the uplaoded ZIP file to /media/public/<zipFileName>

it does create an "index.html" listing the files in this folder (if no index.html exists)

BUT the links in this generated "index.html" are missing the fodler name (i.e. <zipFileName>)


==

an example of this problem:

I uploaded to https://drmattsmith.pythonanywhere.com/ a zip "chris_test.zip"

I can see the generated index.html at:
    - https://drmattsmith.pythonanywhere.com/media/public/chris_test

this index file shows "chuck_norchess.html" as a file

but when I click this file it linjks to URL:
-https://drmattsmith.pythonanywhere.com/media/public/chuck_norchess.html

when it should link to:
https://drmattsmith.pythonanywhere.com/media/public/chris_test/chuck_norchess.html

please fix the code that generated the index.html to the correct links
