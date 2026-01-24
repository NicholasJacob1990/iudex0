#!/bin/bash
curl -X POST "http://127.0.0.1:8000/api/auth/login-test" \
     -H "Content-Type: application/json" \
     -H "Accept: application/json" \
     -v
