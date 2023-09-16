from flask import Flask
import cv2
import pytesseract

cap = cv2.VideoCapture(0)

# Define minimum and maximum dimensions for license plates
min_width = 80
min_height = 40
max_width = 400
max_height = 200

while True:
    ret, frame = cap.read()

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > min_width and h > min_height and w < max_width and h < max_height:
            plate_region = frame[y:y + h, x:x + w]
            plate_text = pytesseract.image_to_string(plate_region, config='--psm 6')

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 0), 2)
            cv2.putText(frame, 'License Plate: ' + plate_text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (0, 0, 0), 2)

    cv2.imshow('License Plate Detection', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):  # Press 'q' to exit
        break

cap.release()
cv2.destroyAllWindows()

app = Flask(__name__)


@app.route('/')
def hello_world():
    return 'Hello World!'


if __name__ == '__main__':
    app.run()
