# Load the browser side of the GUI. 100% totally temporary code to demonstrate the architecture.
WEB_APP_LOADER = """
<html>
<head>
<script>
if(typeof(EventSource)!="undefined") {
   let source = new EventSource("/event-stream");
   source.onmessage=function(event) {
       console.log(event);
       document.getElementById("result").innerHTML += event.data + "<br>";
   }
}
else {
   document.getElementById("result").innerHTML="No EventSource. Please upgrade your browser and try again.";
}
function showWallet() {
    // simple function to demonstrate API call with browser-side processing
    fetch('/wallet')
        .then((response) => response.json())
        .then(data => document.getElementById("result").innerHTML += 'Your wallet has this many keys: ' + data + "<br>")
}
function showHeight() {
    // simple function to demonstrate API call with browser-side processing
    fetch('/height')
        .then((response) => response.json())
        .then(data => document.getElementById("result").innerHTML += 'Your current blockchain height: ' + data + "<br>")
}
</script>
</head>
<body>
(please don't click these until initialization is complete):
<a href="javascript:showWallet()">show wallet</a> | <a href="javascript:showHeight()">show height</a>
<div id="result">Loading...</div>
</body>
</html>
"""
