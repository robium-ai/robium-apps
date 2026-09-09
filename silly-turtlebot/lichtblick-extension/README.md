# Silly TurtleBot Controls

Lichtblick panel for sending natural-language missions to the local guarded
Gemini service and stopping the current robot action. The browser never
receives the Gemini key. Manual driving is deliberately separate in the
layout's native Lichtblick Teleop panel, which publishes bounded `/cmd_vel`
commands only while a direction control is held.
