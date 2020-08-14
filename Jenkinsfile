pipeline {
    agent any

    stages {
        stage('Build api') {
            steps {
                dir('api') {
                    sh 'make build'
                }
            }
        }
        stage('Test api') {
            steps {
                dir('api') {
                    sh 'make test'
                }
            }
        }
        stage('Push api') {
            when {
                branch 'master'
            }
            steps {
                dir('api') {
                    sh 'make push'
                }
            }
        }
    }
}
